import os
import torch as T
import torch.nn.functional as F
import torch.nn as nn
import torch.optim as optim
from torch.distributions.normal import Normal
import numpy as np

# Critico
class CriticNetwork(nn.Module):
    def __init__(self, beta, input_dims, n_actions, fc1_dims=150, fc2_dims=256,
            name='critic', chkpt_dir='tmp/sac'):
        super(CriticNetwork, self).__init__()
        # dimensao do input (posicao_bola, velocidade_bola, posicaoX_robo_1, posicaoY_robo1, vel_robo_1, ang_robo_1, posicaoX_robo_2...)
        self.input_dims = input_dims
        # primeira camada da rede 
        self.fc1_dims = fc1_dims
        # segunda camada da rede
        self.fc2_dims = fc2_dims
        # output da rede
        self.n_actions = n_actions
        # nome da rede
        self.name = name
        # diretorio para salvar o modelo da rede neural
        self.checkpoint_dir = chkpt_dir
        self.checkpoint_file = os.path.join(self.checkpoint_dir, name+'_sac')

        # montando as camadas da rede
        self.fc1 = nn.Linear(self.input_dims[0]+n_actions, self.fc1_dims)
        self.fc2 = nn.Linear(self.fc1_dims, self.fc2_dims)
        self.q = nn.Linear(self.fc2_dims, 1)

        # otimizador de treinamento
        self.optimizer = optim.Adam(self.parameters(), lr=beta)
        # hardware usado para treinar (cuda = GPU (nvidea), )
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')

        self.to(self.device)

    # calculo e retorno do output
    def forward(self, state, action):
        # primeira camada recebe estado e acao e retorna output
        action_value = self.fc1(T.cat([state, action], dim=1))
        # funcao de ativacao do output da primeira rede (no backpropagation evita da derivada zerar)
        action_value = F.relu(action_value)
        # segunda camada pega o output da primeira (pos ativacao) como input e calcula seu proprio output
        action_value = self.fc2(action_value)
        # funcao de ativacao do output da primeira rede (no backpropagation evita da derivada zerar)
        action_value = F.relu(action_value)

        # avialiacao da acao em relacao ao estado
        q = self.q(action_value)

        return q

    def save_checkpoint(self):
        # salva modelo da rede neural atual
        T.save(self.state_dict(), self.checkpoint_file)

    def load_checkpoint(self):
        # carrega modelo previamente treinado
        self.load_state_dict(T.load(self.checkpoint_file))

class ValueNetwork(nn.Module):
    def __init__(self, beta, input_dims, fc1_dims=512, fc2_dims=512,
            name='value', chkpt_dir='tmp/sac'):
        super(ValueNetwork, self).__init__()
        self.input_dims = input_dims
        self.fc1_dims = fc1_dims
        self.fc2_dims = fc2_dims
        self.name = name
        self.checkpoint_dir = chkpt_dir
        self.checkpoint_file = os.path.join(self.checkpoint_dir, name+'_sac')

        self.fc1 = nn.Linear(*self.input_dims, self.fc1_dims)
        self.fc2 = nn.Linear(self.fc1_dims, fc2_dims)
        self.v = nn.Linear(self.fc2_dims, 1)

        self.optimizer = optim.Adam(self.parameters(), lr=beta)
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')

        self.to(self.device)

    def forward(self, state):
        state_value = self.fc1(state)
        state_value = F.relu(state_value)
        state_value = self.fc2(state_value)
        state_value = F.relu(state_value)

        v = self.v(state_value)

        return v

    def save_checkpoint(self):
        T.save(self.state_dict(), self.checkpoint_file)

    def load_checkpoint(self):
        self.load_state_dict(T.load(self.checkpoint_file))


# Ator

class ActorNetwork(nn.Module):
    def __init__(self, alpha, input_dims, max_action, fc1_dims=150, 
            fc2_dims=256, n_actions=2, name='actor', chkpt_dir='tmp/sac'):
        super(ActorNetwork, self).__init__()
        self.input_dims = input_dims
        self.fc1_dims = fc1_dims
        self.fc2_dims = fc2_dims
        self.n_actions = n_actions
        self.name = name
        self.checkpoint_dir = chkpt_dir
        self.checkpoint_file = os.path.join(self.checkpoint_dir, name+'_sac')
        self.max_action = max_action
        self.reparam_noise = 1e-6

        self.fc1 = nn.Linear(*self.input_dims, self.fc1_dims)
        self.fc2 = nn.Linear(self.fc1_dims, self.fc2_dims)
        self.mu = nn.Linear(self.fc2_dims, self.n_actions)
        self.sigma = nn.Linear(self.fc2_dims, self.n_actions)

        self.optimizer = optim.Adam(self.parameters(), lr=alpha)
        self.device = T.device('cuda:0' if T.cuda.is_available() else 'cpu')

        self.to(self.device)

    #calculo do output do ator
    def forward(self, state):
        # primeira camada recebe o estado do ambiente e calcula output
        prob = self.fc1(state)
        # funcao de ativacao
        prob = F.relu(prob)
        # segunda camada recebe como input o output (pos ativacao) da primeira camada e calcula o output
        prob = self.fc2(prob)
        # funcao de ativacao
        prob = F.relu(prob)

        # utilizamos o output para calcular a curva normal (mu e sigma), utilizando um pouco de noise
        mu = self.mu(prob)
        sigma = self.sigma(prob)

        sigma = T.clamp(sigma, min=self.reparam_noise, max=1)

        return mu, sigma

    # retorna acao
    def sample_normal(self, state, reparameterize=True):
        # calcula a curva normal das probabilidades de acoes
        mu, sigma = self.forward(state)
        probabilities = Normal(mu, sigma)

        if reparameterize:
            actions = probabilities.rsample()
        else:
            actions = probabilities.sample()

        # calcula a acao aleatorizando (de acordo com probabilidades da curva normal) o output
        action = T.tanh(actions)*T.tensor(self.max_action).to(self.device)
        log_probs = probabilities.log_prob(actions)
        log_probs -= T.log(1-action.pow(2)+self.reparam_noise)
        log_probs = log_probs.sum(1, keepdim=True)

        # retorno da acao do agente
        return action, log_probs

    def save_checkpoint(self):
        T.save(self.state_dict(), self.checkpoint_file)

    def load_checkpoint(self):
        self.load_state_dict(T.load(self.checkpoint_file))
        