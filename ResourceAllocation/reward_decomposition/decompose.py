import matplotlib.pyplot as plt
import numpy as np
import torch as th
import torch.nn as nn
import itertools

from ResourceAllocation.reward_decomposition.decomposer import *

from mpl_toolkits.axes_grid1 import make_axes_locatable

import time
(
    RAW,
    FLAT_RAW,
    PRED,
    CLASSES,
    LOCAL_REWARDS,
    AGENT_REWARDS
) = range(6)

def train_decomposer(decomposer, batch_memories, reward_optimizer):
    # organize the data
    reward_inputs, global_rewards, _ = build_reward_data(batch_memories)
    raw_outputs = decomposer.forward(reward_inputs)

    local_rewards = decomposer.convert_raw_outputs(raw_outputs)

    output = compute_loss(local_rewards, global_rewards)

    # Now add the regularizing loss
    # output += decomposer.compute_regularization(raw_outputs)

    reward_optimizer.zero_grad()
    output.backward()
    reward_optimizer.step()

def decompose(decomposer, batch_memories):
    # decompose the reward
    reward_inputs, global_rewards, _ = build_reward_data(batch_memories)
    raw_outputs = decomposer.forward(reward_inputs)
    agent_rewards = decomposer.convert_raw_outputs(raw_outputs)
    return agent_rewards


# Function recvs the true global reward and the outputs generated by the decomposer, and checks how similar they are
# This will determine if the QLearner should use each modified sample
def build_reward_mask(decomposer, local_rewards, global_rewards, mask):
    diff = compute_diff(local_rewards, global_rewards, mask)

    # Determine the reward mask and the status
    delta = decomposer.args.reward_diff_threshold * decomposer.n_agents
    reward_mask = th.where(th.logical_and(mask, (th.abs(diff) < delta)), 1., 0.)
    reward_decomposition_acc = th.sum(reward_mask) / th.sum(mask)
    status = reward_decomposition_acc > decomposer.args.reward_acc

    # Visualize inverse histogram if necessary
    print(f"Decomposition Accuracy: {reward_decomposition_acc}")
    # visualize_diff(diff, mask, horiz_line=decomposer.args.reward_diff_threshold)
    return status, reward_mask


def build_reward_data(batch_memories):
    inputs = {}
    truth = {}
    for m in range(tohp.nodes_num):
        inputs[m] = batch_memories[m][:, :RLhp.NUM_STATES]
        truth[m] = batch_memories[m][:, RLhp.NUM_STATES+1: RLhp.NUM_STATES+2]
    global_reward = 0
    for i in range(tohp.nodes_num):
        global_reward += batch_memories[i][:, RLhp.NUM_STATES + 1: RLhp.NUM_STATES + 2]
    outputs = torch.from_numpy(global_reward)
    return inputs, outputs, truth


# huber loss
def huber(diff, delta=0.1):
    loss = th.where(th.abs(diff) < delta, 0.5 * (diff ** 2),
                    delta * th.abs(diff) - 0.5 * (delta ** 2))
    return th.sum(loss) / len(diff)


# log cosh loss
def logcosh(diff):
    loss = th.log(th.cosh(diff))
    return th.sum(loss) / len(diff)


def mse(diff):
    return th.sum(diff ** 2) / len(diff)


def mae(diff):
    return th.sum(th.abs(diff)) / len(diff)


def compute_loss(local_rewards, global_rewards):
    diff = compute_diff(local_rewards, global_rewards).flatten()
    loss = logcosh(diff)
    return loss


def compute_diff(local_rewards, global_rewards):
    # reshape local rewards
    local_rewards = th.reshape(local_rewards, shape=(*local_rewards.shape[:2], -1))
    summed_local_rewards = local_to_global(local_rewards)
    global_rewards = th.reshape(global_rewards, summed_local_rewards.shape)

    diff = summed_local_rewards - global_rewards
    return diff


def almost_flatten(arr):
    return arr.reshape(-1, arr.shape[-1])


def local_to_global(arr):
    return th.sum(arr, dim=-1, keepdims=True)
