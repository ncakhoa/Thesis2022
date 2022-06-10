import argparse
import datetime
import glob
import logging
import os
import re
from pathlib import Path
from typing import List

import torch
import torch.backends.cudnn
from eval_utils import eval_utils
from torch import distributed, nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

import pcdet.datasets
import pcdet.models.detectors
from pcdet.config import cfg, cfg_from_list, cfg_from_yaml_file, log_config_to_file


def parse_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("cfg_path", type=Path)
    parser.add_argument("ckpt", type=Path)

    parser.add_argument("--batch_size", type=int, help="Batch size per GPU")
    parser.add_argument("--num_workers", type=int, default=2)
    parser.add_argument(
        "--set", dest="set_cfgs", nargs=argparse.REMAINDER, help="set extra config keys if needed"
    )
    parser.add_argument("--start_epoch", type=int, default=0)
    parser.add_argument(
        "--eval_all", action="store_true", default=False, help="whether to evaluate all checkpoints"
    )
    parser.add_argument(
        "--ckpt_dir", type=str, help="specify a ckpt directory to be evaluated if needed"
    )
    parser.add_argument("--save_to_file", action="store_true", default=False)
    args = parser.parse_args()

    cfg_from_yaml_file(args.cfg_path, cfg)
    if args.set_cfgs is not None:
        cfg_from_list(args.set_cfgs, cfg)
    return args, cfg


def main():
    args, conf = parse_config()
    distributed.init_process_group(backend="nccl")
    torch.backends.cudnn.benchmark = True
    local_rank = int(os.environ["LOCAL_RANK"])

    batch_size = (
        conf.OPTIMIZATION.BATCH_SIZE_PER_GPU if args.batch_size is None else args.batch_size
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ckpt_dir = args.output_dir / "ckpt"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    eval_dir = args.output_dir / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)

    log_path = args.output_dir / f"log_eval_{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
    logger = create_logger(log_path, local_rank)

    logger.info("Total batch size: %d", distributed.get_world_size() * batch_size)
    log_config_to_file(conf, logger)

    val_loader = build_dataloader(conf.DATA_CONFIG, batch_size, args.num_workers, conf.CLASS_NAMES)

    model_fn = getattr(pcdet.models.detectors, conf.MODEL.NAME)
    model = model_fn(conf.MODEL, len(conf.CLASS_NAMES), train_set)
    model.load_params_from_file(args.ckpt, logger)
    model.cuda(local_rank)
    model = nn.parallel.DistributedDataParallel(model, device_ids=[local_rank])
    logger.info(model)

    eval_utils.eval_one_epoch(
        cfg, model, val_loader, local_rank, logger, args.save_to_file, eval_dir
    )


def build_dataloader(data_cfg, batch_size: int, num_workers: int, class_names: List[str]):
    val_set_fn = getattr(pcdet.datasets, data_cfg.DATASET)
    val_set = val_set_fn(data_cfg, class_names, training=True)
    val_sampler = pcdet.datasets.FlatDistSampler(val_set)
    val_loader = DataLoader(
        val_set,
        batch_size,
        collate_fn=val_set.collate_batch,
        num_workers=num_workers,
        pin_memory=True,
        sampler=val_sampler,
    )
    return val_loader


def create_logger(log_file, rank):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO if rank == 0 else logging.WARNING)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO if rank == 0 else logging.WARNING)
    logger.addHandler(console)
    if log_file is not None:
        file_handler = logging.FileHandler(filename=log_file)
        file_handler.setLevel(logging.INFO if rank == 0 else logging.WARNING)
        logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def get_no_evaluated_ckpt(ckpt_dir, ckpt_record_file, args):
    ckpt_list = glob.glob(os.path.join(ckpt_dir, "*checkpoint_epoch_*.pth"))
    ckpt_list.sort(key=os.path.getmtime)
    evaluated_ckpt_list = [float(x.strip()) for x in open(ckpt_record_file, "r").readlines()]

    for cur_ckpt in ckpt_list:
        num_list = re.findall("checkpoint_epoch_(.*).pth", cur_ckpt)
        if num_list.__len__() == 0:
            continue

        epoch_id = num_list[-1]
        if "optim" in epoch_id:
            continue
        if float(epoch_id) not in evaluated_ckpt_list and int(float(epoch_id)) >= args.start_epoch:
            return epoch_id, cur_ckpt
    return -1, None


if __name__ == "__main__":
    main()
