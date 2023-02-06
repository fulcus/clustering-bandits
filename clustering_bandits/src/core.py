import numpy as np
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor


class Core:
    def __init__(self, environment, agent):
        self.environment = environment
        self.agent = agent

    def simulation(self, n_epochs, n_rounds, parallel=False):
        args = [(deepcopy(self.agent), deepcopy(
            self.environment.reset(i)), n_rounds) for i in range(n_epochs)]
        rewards = []
        a_hists = []
        if parallel:
            with ProcessPoolExecutor(max_workers=4) as executor:
                for rews_epoch, actions_epoch in executor.map(self.helper, args):
                    rewards.append(rews_epoch)
                    a_hists.append(actions_epoch)
        else:
            for arg in args:
                rews_epoch, actions_epoch = self.helper(arg)
                rewards.append(rews_epoch)
                a_hists.append(actions_epoch)
        return np.array(rewards), np.array(a_hists)

    def helper(self, arg):
        return self.epoch(arg[0], arg[1], arg[2])

    def epoch(self, agent, environment, n_rounds=10):
        for _ in range(n_rounds):
            # x_i = environment.get_context()
            context_indexes = environment.get_contexts()
            # new_a = agent.pull_arm(context_i=x_i)
            actions = agent.pull_arms(context_indexes)
            # actions: one row per context
            # environment.round(new_a)
            rewards = environment.round_all(actions)
            # agent.update(rewards)
            agent.update_arms(rewards)
        return environment.rewards, agent.a_hist
