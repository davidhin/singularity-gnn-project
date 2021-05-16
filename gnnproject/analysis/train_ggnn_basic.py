# %% SETUP
import argparse
import datetime
import json
import pickle as pkl
from collections import Counter
from glob import glob

import gnnproject as gp
import gnnproject.helpers.dgl_helpers as dglh
import gnnproject.helpers.representation_learning as rlm
import torch
import torch.optim as optim
from torch import nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from tqdm import tqdm

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default="devign_ffmpeg_qemu",
        choices=["devign_ffmpeg_qemu"],
    )
    parser.add_argument(
        "--variation", default="cfgdfg", choices=["cfg", "cfgdfg", "cpg"]
    )
    parser.add_argument("--batch_size", default=64, type=int)
    parser.add_argument("--learn_rate", default=0.0001, type=float)
    parser.add_argument("--in_num", default=169, type=int)
    parser.add_argument("--out_num", default=200, type=int)
    parser.add_argument("--split_seed", default=0, type=int)
    parser.add_argument("--patience", default=30, type=int)
    try:
        args = parser.parse_args()
    except:
        args = parser.parse_args([])
    gp.debug(args)

    # %% Load own feature extracted graphs
    dgl_proc_files = glob(
        str(gp.processed_dir() / f"{args.dataset}_dgl_{args.variation}/*")
    )
    train, val, test = dglh.train_val_test(dgl_proc_files, seed=args.split_seed)
    print(len(train), len(val), len(test))
    trainset = dglh.CustomGraphDataset(train)
    valset = dglh.CustomGraphDataset(val)
    testset = dglh.CustomGraphDataset(test)
    gp.debug(Counter([int(i) for i in trainset.labels]))
    gp.debug(Counter([int(i) for i in valset.labels]))
    gp.debug(Counter([int(i) for i in testset.labels]))

    # %% Get dataloader
    dl_args = {
        "batch_size": args.batch_size,
        "shuffle": True,
        "collate_fn": dglh.collate,
    }
    train_loader = DataLoader(trainset, **dl_args)
    val_loader = DataLoader(valset, **dl_args)
    test_loader = DataLoader(testset, **dl_args)

    # %% Get DL model
    model = dglh.BasicGGNN(args.in_num, args.out_num, 2)
    loss_func = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=args.learn_rate, weight_decay=0.001)
    savedir = gp.get_dir(gp.processed_dir() / "dl_models")
    ID = datetime.datetime.now().strftime(
        "%Y%m%d%H%M_{}".format("_".join([f"{v}" for k, v in vars(args).items()]))
    )
    savepath = savedir / f"best_basic_ggnn_{ID}.bin"
    model = model.to("cuda")

    # %% Start Tensorbaord
    writer = SummaryWriter(savedir / "best_basic_ggnn" / ID)

    # %% Train DL model
    model.train()
    epoch_losses = []
    best_f1 = 0
    patience = 0
    for epoch in range(500):
        epoch_loss = 0
        with tqdm(train_loader) as tepoch:
            for iter, (bg, label) in enumerate(tepoch):
                if len(epoch_losses) > 0:
                    tepoch.set_description(
                        f"Epoch {epoch} (loss: {round(epoch_losses[-1], 4)})"
                    )
                else:
                    tepoch.set_description(f"Epoch {epoch}")

                output = model(bg)

                loss = loss_func(output, label)
                tepoch.set_postfix(loss=loss.item())
                epoch_loss += loss.detach().item()

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            # ...log the running loss
            epoch_loss /= iter + 1
            epoch_losses.append(epoch_loss)
            writer.add_scalar(
                "Epoch Loss", epoch_loss, epoch * len(train_loader) + iter
            )

        scores = dglh.eval_model(model, val_loader)
        for s in scores.items():
            writer.add_scalar(s[0], s[1], epoch * len(train_loader) + iter)

        if scores["f1"] > best_f1:
            best_f1 = scores["f1"]
            with open(savepath, "wb") as f:
                torch.save(model.state_dict(), f)
            gp.debug(f"Best model saved. {scores} Patience: {patience}")
            patience = 0
        else:
            patience += 1
            gp.debug(f"No improvement. Patience: {patience}")

        if patience > args.patience:
            gp.debug("Training Complete.")
            break

    # %% Evaluate scores on splits
    model.load_state_dict(torch.load(savepath))
    ggnn_results_train = dglh.eval_model(model, train_loader)
    ggnn_results_val = dglh.eval_model(model, val_loader)
    ggnn_results_test = dglh.eval_model(model, test_loader)

    # %% Get and save intermediate representations
    dl_args = {"batch_size": 128, "shuffle": False, "collate_fn": dglh.collate}
    train_loader = DataLoader(trainset, **dl_args)
    val_loader = DataLoader(valset, **dl_args)
    test_loader = DataLoader(testset, **dl_args)
    train_graph_rep = dglh.get_intermediate(model, train_loader)
    val_graph_rep = dglh.get_intermediate(model, val_loader)
    test_graph_rep = dglh.get_intermediate(model, test_loader)

    with open(
        gp.processed_dir() / "dl_models" / f"basic_ggnn_{ID}_hidden_train.pkl", "wb"
    ) as f:
        pkl.dump(train_graph_rep, f)
    with open(
        gp.processed_dir() / "dl_models" / f"basic_ggnn_{ID}_hidden_val.pkl", "wb"
    ) as f:
        pkl.dump(val_graph_rep, f)
    with open(
        gp.processed_dir() / "dl_models" / f"basic_ggnn_{ID}_hidden_test.pkl", "wb"
    ) as f:
        pkl.dump(test_graph_rep, f)

    # %% Get representation learning results
    rlearning_results_train, rlearning_results_test = rlm.representation_learning(
        gp.processed_dir() / "dl_models" / f"basic_ggnn_{ID}_hidden_train.pkl",
        gp.processed_dir() / "dl_models" / f"basic_ggnn_{ID}_hidden_test.pkl",
    )

    # %% Save results
    final_savedir = gp.get_dir(gp.outputs_dir())
    with open(final_savedir / "basic_ggnn_results.csv", "a") as f:
        f.write(
            ",".join(
                [
                    ID,
                    json.dumps(ggnn_results_train),
                    json.dumps(ggnn_results_val),
                    json.dumps(ggnn_results_test),
                    json.dumps(rlearning_results_train),
                    json.dumps(rlearning_results_test),
                ]
            )
        )
