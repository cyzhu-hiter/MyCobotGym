import datetime
import gymnasium
import sys
sys.modules["gym"] = gymnasium
from stable_baselines3 import SAC, HerReplayBuffer, TD3, PPO, DDPG, A2C
from stable_baselines3.common.callbacks import EvalCallback
import mycobotgym.envs
import argparse
import multiprocessing
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.utils import set_random_seed
import gymnasium_robotics.envs


def make_env(env_id, rank, controller_type=None, seed=0):
    """
    Utility function for multiprocessed env.

    :param env_id: (str) the environment ID
    :param num_env: (int) the number of environments you wish to have in subprocesses
    :param seed: (int) the inital seed for RNG
    :param rank: (int) index of the subprocess
    """
    def _init():
        if controller_type:
            env = Monitor(gymnasium.make(
                env_id, controller_type=controller_type, render_mode=render_mode))
        else:
            env = Monitor(gymnasium.make(
                env_id, render_mode=render_mode))
        env.reset(seed=seed + rank)
        return env
    set_random_seed(seed)
    return _init


if __name__ == "__main__":

    num_cpu = multiprocessing.cpu_count()

    parser = argparse.ArgumentParser(prog="MyCobot-Train")

    parser.add_argument("-t", "--total-timesteps", type=int,
                        default=1000, help="Total timesteps for training per env")
    parser.add_argument("-i", "--log-interval", type=int,
                        default=1, help="Number episodes before logging")
    parser.add_argument("--device", type=str,
                        default="auto", help="Training Device")
    parser.add_argument("--eval-freq", type=int,
                        default=1000, help="Number of timesteps before evalution")
    parser.add_argument("-n", "--num-env", type=int, default=num_cpu,
                        help="Number of parallel environment instances")
    parser.add_argument("-o", "--model-output-dir", type=str,
                        default="./trained_model/", help="The output directory to store the trained model")
    parser.add_argument("--log-dir", type=str,
                        default="./log-dir/", help="The log directory to log the training results")
    parser.add_argument("--tensorboard-dir", type=str,
                        default="./tensorboard-log/", help="The tensorboard log directory model")
    parser.add_argument("--her", action='store_true',
                        help="Enable Hindsight Experience Replay")
    parser.add_argument("--algo", type=str, default="SAC",
                        choices=["SAC", "DDPG", "TD3", "PPO", "A2C"], help="Training algorithm [PPO, SAC, TD3, DDPG]")
    parser.add_argument("-c", "--controller-type", type=str,
                        choices=["joint", "mocap", "IK"], help="Controller type 1)Inverse Kinematics (IK) 2) Mocap 3) Joint position control")
    parser.add_argument("--human", action="store_true",
                        help="Enable human render mode")
    parser.add_argument("-m", "--multiproc", action="store_true",
                        help="Enable multiprocessor training")
    parser.add_argument("-e", "--env", type=str, default="ReachObjectEnv-Dense-v0", choices=[
                        "ReachObjectEnv-Dense-v0", "ReachObjectEnv-Sparse-v0", "PickAndPlaceEnv-Dense-v0", "PickAndPlaceEnv-Sparse-v0", "FetchPickAndPlace-v2", "FetchReach-v3"], help="Environment")
    parser.add_argument("-v", "--verbose", type=int, default=2,
                        help="Verbosity level: 0 for no output, 1 for info messages (such as device or wrappers used), 2 for debug messages")
    args = parser.parse_args()

    algos = {"PPO": PPO, "SAC": SAC, "DDPG": DDPG, "TD3": TD3, "A2C": A2C}

    render_mode = "human" if args.human else None

    vec_env_cls = SubprocVecEnv if args.multiproc else DummyVecEnv

    out_name = f"{args.env}-{args.total_timesteps:_d}-{args.algo}-{'HER-' if args.her else ''}{args.controller_type}-{vec_env_cls.__name__}-{datetime.datetime.now():%Y-%m-%d %H:%M:%S}"

    env = vec_env_cls([make_env(args.env, i, args.controller_type)
                       for i in range(args.num_env)])

    eval_callback = EvalCallback(env, best_model_save_path=args.model_output_dir + out_name,
                                 eval_freq=max(args.eval_freq // args.num_env, 1), deterministic=True, render=False)
    if args.her:
        assert args.algo in ["DDPG", "TD3",
                             "SAC"], "HER only works with DDPG, TD3, SAC"
        assert args.num_env == 1, "HER does not support multiple environment instances"
        replay_buffer_cls = HerReplayBuffer
        replay_buffer_dict = dict(
            n_sampled_goal=4, goal_selection_strategy="future", online_sampling=True)
        model = algos[args.algo]("MultiInputPolicy", env, replay_buffer_class=replay_buffer_cls,
                                 replay_buffer_kwargs=replay_buffer_dict, gradient_steps=-1, tensorboard_log=args.tensorboard_dir + out_name, verbose=args.verbose, device=args.device)
    else:
        if args.algo in ["PPO", "A2C"]:
            model = algos[args.algo](
                "MultiInputPolicy", env, n_steps=args.total_timesteps, tensorboard_log=args.tensorboard_dir + out_name, verbose=args.verbose, device=args.device)
        else:
            model = algos[args.algo](
                "MultiInputPolicy", env, tensorboard_log=args.tensorboard_dir + out_name, verbose=args.verbose, train_freq=(1, "step"), device=args.device)

    model.learn(args.total_timesteps * args.num_env, progress_bar=True,
                log_interval=args.log_interval, callback=eval_callback)

    env.close()
