import numpy as np


class LinearEnvironment:
    def __init__(self, n_rounds, theta, noise_std=0.01, random_state=1):
        self.n_rounds = n_rounds
        self.theta = theta
        self.noise_std = noise_std
        self.random_state = random_state
        self.t = None
        self.noise = None
        self.rewards = None
        self.reset(0)

    def round(self, action):
        obs_reward = self.theta @ action + self.noise[self.t]
        self.rewards = np.append(self.rewards, obs_reward)
        self.t += 1

    def reset(self, i=0):
        self.t = 0
        np.random.seed(self.random_state + i)
        self.noise = np.random.normal(0, self.noise_std, self.n_rounds)
        return self


class ContextualLinearEnvironment(LinearEnvironment):
    def __init__(self, n_rounds, contexts, theta, psi=None, noise_std=0.01, random_state=1):
        super().__init__(n_rounds, theta, noise_std, random_state)
        self.contexts = contexts
        if psi is None:  # psi(a) = a
            self.psi = lambda a, x: a
        else:
            self.psi = psi
        self.reset()

    def round(self, action):
        obs_reward = (self.theta @ self.psi(action, self.last_context)
                      + self.noise[self.t])
        self.rewards = np.append(self.rewards, obs_reward)
        self.t += 1

    def get_context(self):
        self.last_context = np.random.choice(self.contexts)
        return np.random.choice(self.contexts)


class ProductEnvironment(ContextualLinearEnvironment):
    def __init__(self, n_rounds, contexts, theta, theta_p, psi=None, noise_std=0.01, random_state=1):
        super().__init__(n_rounds, contexts, theta, theta_p, psi, noise_std, random_state)
        self.theta_p = theta_p
        self.reset()

    def round(self, action):
        obs_reward = (self.theta @ self.psi(action, self.last_context)
                      + self.theta_p[self.last_context] @ self.psi(action, self.last_context)
                      + self.noise[self.t])
        self.rewards = np.append(self.rewards, obs_reward)
        self.t += 1
