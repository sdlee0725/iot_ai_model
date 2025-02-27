import torch
import torch.autograd as autograd
import torch.nn as nn
import torch.functional as F
import torch.optim as optim
import numpy as np
from torch.utils.data import DataLoader 
import time
from tqdm import tqdm
import logging
import random
import os
import torchmetrics
from torch.utils.data.dataset import random_split

from dataset import VibrationDataset
from model import RNNModel

logger = logging.getLogger('train_log')

checkpoints_path = "check_points/rnn"

def print_log(text):
    logger.info(text)

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('true', '1'):
        return True
    elif v.lower() in ('false', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def train_model(model, train_loader, val_loader, criterion, optimizer, num_epochs = 1):
    t_loss_hist = np.zeros(num_epochs)
    t_f1_hist = np.zeros(num_epochs)
    v_loss_hist = np.zeros(num_epochs)
    v_f1_hist = np.zeros(num_epochs)

    num_classes = 5

    f1socre = torchmetrics.F1Score(num_classes = num_classes)
    cm = torchmetrics.ConfusionMatrix(num_classes = num_classes)

    early_stopping = 5
    min_loss = 99999.
    early_count = 0
    for epoch in range(num_epochs):
        preds = torch.tensor([],dtype= torch.int16).to(device)
        targets = torch.tensor([],dtype= torch.int16).to(device)

        start_time = time.time()
        avg_cost = 0
        total_batch = len(train_loader)
        progress = tqdm(train_loader)

        model.train()
        for samples in progress:
            _, x_train, y_train = samples
            
            x_train = x_train.to(device)
            y_train = y_train.to(device)
            #seq별 hidden state reset
            model.reset_hidden_state()
            
            # H(x) 계산
            outputs = model(x_train)
            
            # cost 계산
            loss = criterion(outputs, y_train)                    
            
            # cost로 H(x) 개선
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            avg_cost += loss
            
            out = torch.max(outputs.data, 1)[1]
            y = torch.max(y_train.data, 1)[1]

            preds = torch.cat([preds, out])
            targets = torch.cat([targets, y])

            progress.set_postfix({'loss' : loss.item()})

        f1 = f1socre(preds.to('cpu'), targets.to('cpu'))
        avg_cost = avg_cost / total_batch

        t_loss_hist[epoch] = avg_cost 
        t_f1_hist[epoch] = f1

        logger.info('trn Epoch:{:3d}, time : {:.2f}, loss : {:.4f}, f1-score : {:.4f}'
            .format(
                epoch+1, 
                time.time()-start_time,
                avg_cost,
                f1
            )
        )

        preds = torch.tensor([],dtype= torch.int16).to(device)
        targets = torch.tensor([],dtype= torch.int16).to(device)
        start_time = time.time()
        progress = tqdm(val_loader)

        avg_cost = 0
        total_batch = len(train_loader)

        model.eval()
        with torch.no_grad():
            for samples in progress:
                _, x_train, y_train = samples
            
                x_train = x_train.to(device)
                y_train = y_train.to(device)

                # H(x) 계산
                outputs = model(x_train)
                loss = criterion(outputs, y_train)  
                avg_cost += loss
                
                out = torch.max(outputs.data, 1)[1]
                y = torch.max(y_train.data, 1)[1]

                preds = torch.cat([preds, out])
                targets = torch.cat([targets, y])  

        f1 = f1socre(preds.to('cpu'), targets.to('cpu'))
        avg_cost = avg_cost / total_batch
        
        # if avg_cost >= min_loss:
        #     early_count += 1
        #     if early_count >= early_stopping:
        #         break
        # else:
        #     min_loss = avg_cost
        #     early_count = 0

        if len(v_f1_hist) > 0 and max(v_f1_hist) < f1:
            save_path = f'{checkpoints_path}/model_state_dict_best.pt'
            logger.info(f'best f1! save model. {save_path}')
            torch.save(model.state_dict(), save_path)
        
        v_loss_hist[epoch] = avg_cost 
        v_f1_hist[epoch] = f1
            
        logger.info('val Epoch:{:3d}, time : {:.2f}, loss : {:.4f}, f1-score : {:.4f}'
            .format(
                epoch+1, 
                time.time()-start_time,
                avg_cost,
                f1
            )
        )

    # validation matric
    logger.info(cm(preds.cpu(), targets.cpu()))

    return t_loss_hist, t_f1_hist, v_loss_hist, v_f1_hist


if __name__ == "__main__" :
    import argparse

    start_time = time.time()

    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--name', dest='name', type=str, default='rnn')
    parser.add_argument('--seed', dest='random_seed', type=int, default=45)
    parser.add_argument('--lr', dest='lr', type=float, default=0.01)
    parser.add_argument('--epochs', dest='epochs', type=int, default=50)
    # parser.add_argument('--step_size', dest='step_size', type=int, default=20)
    parser.add_argument('--batch_size', dest='batch_size', type=int, default=256)
    # parser.add_argument('--weight_decay', dest='weight_decay', type=float, default=0.4)
    # parser.add_argument('--pretrained', dest='pretrained', type=bool, default=False)
    # parser.add_argument('--gamma', dest='gamma', type=float, default=0.1)
    # parser.add_argument('--test', dest='test_path', default='', type=str)
    # parser.add_argument('--patience', dest='patience', default=40, type=int)
    parser.add_argument('--cpus', dest='cpus', default=-1, type=int)
    parser.add_argument('--hidden_dim', dest='hidden_dim', default=8, type=int)
    parser.add_argument('--layers', dest='layers', default=2, type=int)
    parser.add_argument('--use_cpu', dest='use_cpu', type=str2bool, default=False)
    # parser.add_argument('--augmentation', dest='augmentation', type=bool, default=False)

    args = parser.parse_args()

    # setup training
    training_name = args.name
    random_seed = args.random_seed
    epochs = args.epochs
    # step_size = args.step_size
    lr = args.lr
    # pretrained = args.pretrained
    # weight_decay = args.weight_decay
    # gamma = args.gamma
    # test_model_path = args.test_path
    # patience = args.patience
    # augmentation = args.augmentation
    batch_size = args.batch_size

    # setup rnn structure
    seq = 3
    input_dim = 18
    hidden_dim = args.hidden_dim
    output_dim = 5
    layers = args.layers

    if args.cpus <= 0:
        cpus = os.cpu_count() - 1 
    else:
        cpus = min(args.cpus, os.cpu_count() - 1)

    random.seed(random_seed)
    np.random.seed(random_seed)
    torch.manual_seed(random_seed)
    torch.cuda.manual_seed(random_seed)
    torch.cuda.manual_seed_all(random_seed) # if use multi-GPU
    g = torch.Generator()
    g.manual_seed(random_seed)
    # torch.backends.cudnn.deterministic = True
    # torch.use_deterministic_algorithms(True)
    # torch.backends.cudnn.benchmark = False

    # train_path = "/content/dataset/train"
    # test_path = "/content/dataset/test"

    device = torch.device("cuda" if (not args.use_cpu) and torch.cuda.is_available() else "cpu")

    # path = 'dataset/iot_sensor_pickle/*.pk'
    # dataset = VibrationDataset(info_file_path)
    
    path = 'dataset/vibration/train/**/*.csv'
    dataset = VibrationDataset(path)

    training_size = int(len(dataset) * 0.8)
    valid_size = len(dataset) - training_size
    trn_dataset, val_dataset = random_split(dataset, [training_size, valid_size], generator = torch.Generator().manual_seed(random_seed))

    trn_dataloader = DataLoader(trn_dataset,
                            batch_size=batch_size,
                            shuffle=True,
                            num_workers=cpus,
                            pin_memory=True,
                            drop_last=False)
    
    val_dataloader = DataLoader(val_dataset,
                            batch_size=10240,
                            shuffle=False,
                            num_workers=cpus,
                            pin_memory=True,
                            drop_last=False)

        # 모델 학습습 로깅깅 설정
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    if not os.path.exists(checkpoints_path):
        os.makedirs(checkpoints_path)

    logging_path = "{}/train.log".format(checkpoints_path)
    fh = logging.FileHandler(filename=logging_path)
    fh.setLevel(logging.INFO)
    logger.addHandler(ch)
    logger.addHandler(fh)

    logger.info('logging file path : {}'.format(logging_path))
    logger.info('training device : {}'.format(device))
    logger.info(args)
    
    logger.info('data size - trn : {}, val : {}'.format(training_size, valid_size))

    model = RNNModel(input_dim, hidden_dim, seq, output_dim, layers).to(device)  
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr = lr)
    train_hist = train_model(model, trn_dataloader, val_dataloader, criterion, optimizer, num_epochs = epochs)