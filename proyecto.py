# -*- coding: utf-8 -*-
"""Proyecto

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1UoYhRtR9mYx-G_BZ2_dc7UEI6SErqxYZ

# Proyecto
## Integrantes
- Camilo Soria
- Nicole Caballero
- Valeria Nazal
"""

# from google.colab import drive
import os

# drive.mount('/content/drive')

# Commented out IPython magic to ensure Python compatibility.
# %cd drive/MyDrive/Ramos/Ramos Computación/Aprendizaje Profundo IIC3697 2023-1/Proyecto

# !git clone https://github.com/brendenlake/SCAN

PATH = "../SCAN"
dirs = [
    file_
    for file_ in os.listdir(PATH)
    if file_.find(".") == -1 and os.path.isdir(os.path.join(PATH, file_))
]
if not os.path.isdir("logs") and not os.path.isdir("models"):
    os.mkdir("logs")
    os.mkdir("models")
    for dir in dirs:
        logs_path = os.path.join("logs", dir)
        models_path = os.path.join("models", dir)
        os.mkdir(logs_path)
        os.mkdir(models_path)
        os.mkdir(os.path.join(logs_path, "train"))
        os.mkdir(os.path.join(logs_path, "test"))
        os.mkdir(os.path.join(models_path, "train"))
        os.mkdir(os.path.join(models_path, "test"))

"""## Language class for vocab modelling"""


class Lang:
    def __init__(self, name: str):
        self.name = name
        self.word2index = {}
        self.word2count = {}
        self.index2word = {0: "SOS", 1: "EOS"}
        self.n_words = 2  # Count SOS and EOS

    def add_sentence(self, sentence: str):
        for word in sentence.split(" "):
            self.add_word(word)

    def add_word(self, word: str):
        if word not in self.word2index:
            self.word2index[word] = self.n_words
            self.word2count[word] = 1
            self.index2word[self.n_words] = word
            self.n_words += 1
        else:
            self.word2count[word] += 1


"""## Encoder"""

from typing import Tuple
import torch
import torch.nn as nn


class CommandEncoder(nn.Module):
    def __init__(
        self,
        input_size: int,
        hidden_size: int = 100,
        n_layers: int = 1,
        dropout: float = 0.1,
        device=torch.device("cpu"),
    ):
        super(CommandEncoder, self).__init__()
        self.hidden_size = hidden_size
        self.embedding = nn.Embedding(input_size, hidden_size, device=device)
        self.lstm = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=n_layers,
            batch_first=True,
        ).to(device)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self, x: torch.Tensor, hidden: torch.Tensor, cell: torch.Tensor
    ) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
        # x: (batch_size, seq_length)?
        embeds = self.dropout(self.embedding(x))
        # embeds: (batch_size, seq_length, hidden_size)
        if hidden is None or cell is None:
            output, (hidden, cell) = self.lstm(embeds)
        else:
            output, (hidden, cell) = self.lstm(embeds, (hidden, cell))
        # output: (batch_size, seq_length, hidden_size)
        # hidden: (n_layers, batch_size, hidden_size)
        # cell: (n_layers, batch_size, hidden_size)
        return output, (hidden, cell)

    def save(self, path: str):
        torch.save(self.state_dict(), path)

    def load(self, path: str):
        self.load_state_dict(torch.load(path))


"""## Decoder

### Attention Models
"""

from typing import Tuple, Union
import torch
import torch.nn as nn
import torch.nn.functional as F


SOS_TOKEN = 0


class LuongAttention(nn.Module):
    def __init__(self, hidden_size: int, device):
        super(LuongAttention, self).__init__()
        self.hidden_size = hidden_size

        self.attn = nn.Linear(hidden_size, hidden_size, device=device)

    def forward(self, decoder_hidden, encoder_outputs):
        # Calculate attention energies
        attn_energies = self.score(decoder_hidden, encoder_outputs)

        # Normalize energies to get attention weights
        attn_weights = F.softmax(attn_energies, dim=0)

        # Calculate the context vector
        context_vector = attn_weights.bmm(encoder_outputs)

        return context_vector, attn_weights

    def score(self, decoder_hidden, encoder_outputs):
        energy = self.attn(encoder_outputs)
        energy = decoder_hidden.bmm(energy.permute(0, 2, 1))
        return energy


class BahdanauAttention(nn.Module):
    def __init__(self, hidden_size: int, device=torch.device("cpu")):
        super(BahdanauAttention, self).__init__()
        self.Wa = nn.Linear(hidden_size, hidden_size, device=device)
        self.Ua = nn.Linear(hidden_size, hidden_size, device=device)
        self.Va = nn.Linear(hidden_size, 1, device=device)

    def forward(
        self, query: torch.Tensor, keys: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        scores = self.Va(torch.tanh(self.Wa(query) + self.Ua(keys)))
        scores = scores.squeeze(2).unsqueeze(1)

        weights = F.softmax(scores, dim=-1)
        # Performs a batch matrix-matrix product of matrices
        context = torch.bmm(weights, keys)

        return context, weights


from typing import Tuple, Union
import torch
import torch.nn as nn
import torch.nn.functional as F

SOS_TOKEN = 0


class ActionDecoder(nn.Module):
    def __init__(
        self,
        output_size: int,
        hidden_size: int,
        n_layers: int,
        dropout: float = 0.1,
        attention: bool = True,
        attention_type: str = "bahdanau",
        device=torch.device("cpu"),
    ):
        super(ActionDecoder, self).__init__()
        self.embedding = nn.Embedding(output_size, hidden_size, device=device)
        if attention:
            self.lstm = nn.LSTM(
                2 * hidden_size, hidden_size, n_layers, batch_first=True
            ).to(device)
            if attention_type == "bahdanau":
                self.attention = BahdanauAttention(hidden_size, device)
            else:
                self.attention = LuongAttention(hidden_size, device)
        else:
            self.attention = None
            self.lstm = nn.LSTM(
                hidden_size, hidden_size, n_layers, batch_first=True
            ).to(device)
        self.out = nn.Linear(hidden_size, output_size, device=device)
        self.dropout = nn.Dropout(dropout)
        self.device = device

    def forward(
        self,
        encoder_outputs: torch.Tensor,
        encoder_hidden: torch.Tensor,
        encoder_cell: torch.Tensor,
        max_length: int,
        target_tensor: Union[torch.Tensor, None] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        batch_size = encoder_outputs.size(0)
        decoder_input = torch.empty(
            batch_size, 1, dtype=torch.long, device=self.device
        ).fill_(SOS_TOKEN)

        decoder_hidden = encoder_hidden
        decoder_cell = encoder_cell
        decoder_outputs = []
        attentions = []

        for i in range(max_length):
            (
                decoder_output,
                decoder_hidden,
                decoder_cell,
                attn_weights,
            ) = self.forward_step(
                decoder_input, decoder_hidden, decoder_cell, encoder_outputs
            )
            decoder_outputs.append(decoder_output)
            attentions.append(attn_weights)

            if target_tensor is not None:
                # Teacher forcing: Feed the target as the next input
                decoder_input = target_tensor[:, i].unsqueeze(1)  # Teacher forcing
            else:
                # Without teacher forcing (for predictions and eval): use its own predictions as the next input
                # torch.topk: A namedtuple of (values, indices) is returned with the values and
                # indices of the largest k elements of each row of the input tensor in the given dimension dim.
                _, topi = decoder_output.topk(1)
                decoder_input = topi.squeeze(
                    -1
                ).detach()  # detach from history as input

        decoder_outputs = torch.cat(decoder_outputs, dim=1)
        decoder_outputs = F.log_softmax(decoder_outputs, dim=-1)
        attentions = torch.cat(attentions, dim=1)

        return decoder_outputs, decoder_hidden, attentions

    def forward_step(
        self,
        input: torch.Tensor,
        hidden: torch.Tensor,
        cell: torch.Tensor,
        encoder_outputs: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, Union[torch.Tensor, None]]:
        attn_weights = None
        if self.attention is not None:
            embedded = self.dropout(self.embedding(input))
            query = hidden.permute(1, 0, 2)
            keys = encoder_outputs
            # FIXME: keys|| encoder_outputs: (batch_size, seq_length, hidden_size)
            #        query|| hidden: ( batch_size, n_layers, hidden_size)
            context, attn_weights = self.attention(query, keys)
            lstm_input = torch.cat((embedded, context), dim=2)
        else:
            output = self.embedding(input)
            lstm_input = F.relu(output)
        output, (hidden, cell) = self.lstm(lstm_input, (hidden, cell))
        output = self.out(output)

        return output, hidden, cell, attn_weights if attn_weights is not None else None

    def save(self, path: str):
        torch.save(self.state_dict(), path)

    def load(self, path: str):
        self.load_state_dict(torch.load(path))


"""## Utilities functions"""

# Commented out IPython magic to ensure Python compatibility.
# %matplotlib inline
import torch
import numpy as np
from typing import Tuple, Union
from torch.utils.data import DataLoader, RandomSampler, TensorDataset
import matplotlib.pyplot as plt

plt.switch_backend("agg")
import matplotlib.ticker as ticker


PATH = "../SCAN"
EOS_TOKEN = 1
if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"
device = torch.device(device)


def read_file(relative_path: str) -> list[str]:
    with open(f"{PATH}/{relative_path}", "r") as f:
        data = f.readlines()
    return data


def preprocess(
    data: list[str],
) -> list[Tuple[str, str]]:
    pairs = []
    for line in data:
        primitives, commands = line[4:].split(" OUT: ")
        commands = commands.strip("\n")
        pairs.append((primitives, commands))
    return pairs


def load_langs(
    input_lang_name: str,
    output_lang_name: str,
    train_data: list[str],
    test_data: list[str],
) -> Tuple[Lang, Lang, list[Tuple[str, str]], list[Tuple[str, str]]]:
    print(
        "Train Split: Read %i %s-%s lines"
        % (len(train_data), input_lang_name, output_lang_name)
    )
    print(
        "Test Split: Read %i %s-%s lines"
        % (len(test_data), input_lang_name, output_lang_name)
    )

    input_lang, output_lang = Lang(input_lang_name), Lang(output_lang_name)
    train_pairs = preprocess(train_data)
    test_pairs = preprocess(test_data)

    for input, output in train_pairs:
        input_lang.add_sentence(input)
        output_lang.add_sentence(output)

    for input, output in test_pairs:
        input_lang.add_sentence(input)
        output_lang.add_sentence(output)
    print("Counted Words")
    print(input_lang.name, input_lang.n_words)
    print(output_lang.name, output_lang.n_words)
    return input_lang, output_lang, train_pairs, test_pairs


def get_max_length(data: list[Tuple[str, str]]) -> int:
    max = 0
    for input, output in data:
        compare_len = len(input) if len(input) > len(output) else len(output)
        if compare_len > max:
            max = compare_len
    return max


def word_to_index(lang: Lang, sentence: str) -> list[int]:
    return [lang.word2index[word] for word in sentence.split(" ")]


def sentence_to_tensor(lang: Lang, sentence: str) -> torch.Tensor:
    indexes = word_to_index(lang, sentence)
    indexes.append(EOS_TOKEN)
    return torch.tensor(indexes, dtype=torch.long, device=device).view(1, -1)


def get_dataloader(
    batch_size: int,
    max_length: int,
    input_lang: Lang,
    output_lang: Lang,
    pairs: list[Tuple[str, str]],
) -> DataLoader:
    n = len(pairs)
    input_ids = np.zeros((n, max_length), dtype=np.int32)
    target_ids = np.zeros((n, max_length), dtype=np.int32)
    input_ids.fill(EOS_TOKEN)
    target_ids.fill(EOS_TOKEN)

    for idx, (inp, tgt) in enumerate(pairs):
        inp_ids = word_to_index(input_lang, inp)
        tgt_ids = word_to_index(output_lang, tgt)
        input_ids[idx, : len(inp_ids)] = inp_ids
        target_ids[idx, : len(tgt_ids)] = tgt_ids

    train_data = TensorDataset(
        torch.LongTensor(input_ids).to(device), torch.LongTensor(target_ids).to(device)
    )

    train_sampler = RandomSampler(train_data)
    train_dataloader = DataLoader(
        train_data, sampler=train_sampler, batch_size=batch_size, drop_last=True
    )
    return train_dataloader


def show_plot(title: str, points: list[float], epoch: int):
    plt.figure()
    fig, ax = plt.subplots()
    # this locator puts ticks at regular intervals
    loc = ticker.MultipleLocator(base=0.2)
    ax.yaxis.set_major_locator(loc)
    plt.title(title)
    plt.ylabel("Epoch")
    plt.plot(range(epoch), points)
    plt.show()


def log_it(
    output_str: str,
    experiment: str,
    epoch: int,
    train: bool = True,
    attention_change: bool = False,
):
    print(output_str)
    path = (
        f"logs/{experiment}/{'train' if train else 'test'}/logs_{epoch}.txt"
        if not attention_change
        else f"logs/{experiment}/{'train' if train else 'test'}/logs_luong_{epoch}.txt"
    )
    with open(path, "a") as f:
        f.write(output_str)


def epoch_loop(
    encoder_hidden: Union[torch.Tensor, None],
    encoder_cell: Union[torch.Tensor, None],
    dataloader: DataLoader,
    encoder: CommandEncoder,
    decoder: ActionDecoder,
    max_length: int,
    encoder_optimizer,
    decoder_optimizer,
    criterion,
    testing: bool = False,
) -> Tuple[float, Union[torch.Tensor, float], torch.Tensor, torch.Tensor]:
    # Training Loop
    input_tensor, target_tensor = next(iter(dataloader))
    encoder_optimizer.zero_grad()
    decoder_optimizer.zero_grad()
    encoder_outputs, (encoder_hidden, encoder_cell) = encoder(
        input_tensor,
        encoder_hidden.detach() if encoder_hidden is not None else None,
        encoder_cell.detach() if encoder_cell is not None else None,
    )
    decoder_outputs, _, _ = decoder(
        encoder_outputs, encoder_hidden, encoder_cell, max_length, target_tensor
    )

    decoder_outputs = decoder_outputs.view(-1, decoder_outputs.size(-1))
    target_tensor = target_tensor.view(-1)
    loss = criterion(decoder_outputs, target_tensor)

    _, topi = decoder_outputs.topk(1)
    topi = topi.squeeze()
    acc = (torch.sum((topi == target_tensor)) / len(target_tensor)).cpu().item()
    if not testing:
        loss.backward()

    encoder_optimizer.step()
    decoder_optimizer.step()

    return loss.item(), acc, encoder_hidden, encoder_cell


"""## Main"""

from torch import nn, optim
from torch.nn import functional as F
import torch
import numpy as np
from typing import Tuple
import random


def evaluate(
    encoder: CommandEncoder,
    decoder: ActionDecoder,
    pair: Tuple[str, str],
    input_lang: Lang,
    output_lang: Lang,
) -> Tuple[list[str], torch.Tensor, float, float]:
    encoder_hidden, encoder_cell = (None, None)
    (input_sentence, input_target) = pair
    with torch.no_grad():
        input_tensor = sentence_to_tensor(input_lang, input_sentence)
        target_tensor = sentence_to_tensor(output_lang, input_target)
        encoder_outputs, (encoder_hidden, encoder_cell) = encoder(
            input_tensor, encoder_hidden, encoder_cell
        )
        decoder_outputs, _, decoder_attn = decoder(
            encoder_outputs, encoder_hidden, encoder_cell, max_length, None
        )

        _, topi = decoder_outputs.topk(1)
        decoded_ids = topi.squeeze()

        decoded_words = []
        for idx in decoded_ids:
            if idx.item() == EOS_TOKEN:
                decoded_words.append("<EOS>")
                break
            decoded_words.append(output_lang.index2word[idx.item()])

        target_tensor = F.pad(
            target_tensor,
            (0, max_length - target_tensor.size(1)),
            "constant",
            EOS_TOKEN,
        )
        topi = topi.squeeze()
        acc = (torch.sum((topi == target_tensor)) / len(target_tensor)).cpu().item()
        loss = criterion(
            decoder_outputs.view(-1, decoder_outputs.size(-1)),
            target_tensor.view(-1),
        )
    return decoded_words, decoder_attn, loss, acc


def evaluate_randomly(
    encoder: CommandEncoder,
    decoder: ActionDecoder,
    input_lang: Lang,
    output_lang: Lang,
    pairs: list[Tuple[str, str]],
) -> str:
    pair = random.choice(pairs)
    output_words, _, loss, acc = evaluate(
        encoder=encoder,
        decoder=decoder,
        pair=pair,
        input_lang=input_lang,
        output_lang=output_lang,
    )
    output_sentence = " ".join(output_words)
    return f"INPUT: {pair[0]}\nTARGET: {pair[1]}\nOUTPUT: {output_sentence}\nLOSS: {loss}\nACC: {acc}\n"


def train_or_test(
    testing: bool = False,
    variant: Union[str, None] = None,
    attention_change: bool = False,
):
    plot_losses = []
    plot_accs = []
    print_loss_total = 0  # Reset every print_every
    plot_loss_total = 0  # Reset every plot_every
    print_acc_total = 0  # Reset every print_every
    plot_acc_total = 0  # Reset every plot_every
    encoder_hidden, encoder_cell = (None, None)
    epochs = hparams["n_epochs"] if not testing else len(test_dataloader)
    for epoch in range(1, epochs + 1):
        if testing:
            encoder.eval()
            decoder.eval()
        else:
            encoder.train()
            decoder.train()
        loss, acc, encoder_hidden, encoder_cell = epoch_loop(
            encoder_hidden=encoder_hidden,
            encoder_cell=encoder_cell,
            dataloader=test_dataloader if testing else train_dataloader,
            encoder=encoder,
            decoder=decoder,
            max_length=max_length,
            encoder_optimizer=encoder_optimizer,
            decoder_optimizer=decoder_optimizer,
            criterion=criterion,
            testing=testing,
        )

        print_loss_total += loss
        print_acc_total += acc
        plot_acc_total += acc
        plot_loss_total += loss

        if epoch % hparams["print_every"] == 0:
            print_loss_avg = print_loss_total / hparams["print_every"]
            print_acc_avg = print_acc_total / hparams["print_every"]
            print_loss_total = 0
            print_acc_total = 0
            output_str = "(Epoch: %d, Progress: %d%%) Loss: %.4f Acc: %.4f" % (
                epoch,
                epoch / hparams["n_epochs"] * 100,
                print_loss_avg,
                print_acc_avg,
            )
            log_it(
                output_str,
                experiment if variant is None else f"{experiment}_{variant}",
                epoch,
                train=(not testing),
                attention_change=attention_change,
            )

        if epoch % hparams["plot_every"] == 0:
            plot_loss_avg = plot_loss_total / hparams["plot_every"]
            plot_losses.append(plot_loss_avg)
            plot_loss_total = 0
            if len(plot_losses) > hparams["plot_every"]:
                show_plot(f"{experiment} losses", plot_losses, epoch)
            plot_acc_avg = plot_acc_total / hparams["plot_every"]
            plot_accs.append(plot_acc_avg)
            plot_acc_total = 0
            if len(plot_losses) > hparams["plot_every"]:
                show_plot(f"{experiment} accuracy", plot_accs, epoch)

        if epoch % hparams["save_every"] == 0:
            if not testing:
                path_encoder = (
                    f"models/{experiment}/encoder_{epoch}.pt"
                    if variant is None
                    else f"models/{experiment}/{variant}_encoder_{epoch}.pt"
                )
                path_decoder = (
                    f"models/{experiment}/decoder_{epoch}.pt"
                    if variant is None
                    else f"models/{experiment}/{variant}_decoder_{epoch}.pt"
                )
                encoder.save(path_encoder)
                decoder.save(path_decoder)
            losses_path = (
                f"logs/{experiment}/{'test' if testing else 'train'}/plot_losses_{epoch}.npy"
                if variant is None
                else f"logs/{experiment}_{variant}/{'test' if testing else 'train'}/plot_losses_{epoch}.npy"
            )
            accs_path = (
                f"logs/{experiment}/{'test' if testing else 'train'}/plot_accs_{epoch}.npy"
                if variant is None
                else f"logs/{experiment}_{variant}/{'test' if testing else 'train'}/plot_accs_{epoch}.npy"
            )
            np.save(
                losses_path,
                plot_losses,
            )
            np.save(
                accs_path,
                plot_accs,
            )

        if epoch % hparams["eval_every"] == 0:
            print("Evaluating: ")
            output_str = evaluate_randomly(
                encoder=encoder,
                decoder=decoder,
                input_lang=input_lang,
                output_lang=output_lang,
                pairs=test_pairs,
            )
            log_it(
                output_str,
                experiment if not variant else f"{experiment}_{variant}",
                epoch,
                train=(not testing),
                attention_change=attention_change,
            )


# """## Experiment 1"""

if __name__ == "__main__":
    hparams = {
        "batch_size": 32,
        "hidden_size": 100,
        "n_epochs": 4000,
        "n_layers": 1,
        "lr": 0.001,
        "dropout": 0.1,
        "print_every": 100,
        "plot_every": 100,
        "save_every": 100,
        "eval_every": 1000,
    }
    experiment = "simple_split"
    train_data = read_file(f"{experiment}/tasks_train_simple.txt")
    test_data = read_file(f"{experiment}/tasks_test_simple.txt")
    # load langs with train and test data, so both have all the words from their respective domains
    input_lang, output_lang, train_pairs, test_pairs = load_langs(
        input_lang_name="primitives",
        output_lang_name="commands",
        train_data=train_data,
        test_data=test_data,
    )

    max_length = get_max_length(train_pairs)

    train_dataloader = get_dataloader(
        batch_size=hparams["batch_size"],
        max_length=max_length,
        input_lang=input_lang,
        output_lang=output_lang,
        pairs=train_pairs,
    )

    test_dataloader = get_dataloader(
        batch_size=hparams["batch_size"],
        max_length=max_length,
        input_lang=input_lang,
        output_lang=output_lang,
        pairs=test_pairs,
    )

    encoder = CommandEncoder(
        input_size=input_lang.n_words,
        hidden_size=hparams["hidden_size"],
        n_layers=hparams["n_layers"],
        dropout=hparams["dropout"],
        device=device,
    )
    # encoder.load(f"models/{experiment}/encoder_10000.pt")
    decoder = ActionDecoder(
        output_size=output_lang.n_words,
        hidden_size=hparams["hidden_size"],
        n_layers=hparams["n_layers"],
        dropout=hparams["dropout"],
        attention=True,
        attention_type="luong",
        device=device,
    )
    # decoder.load(f"models/{experiment}/decoder_10000.pt")

    encoder_optimizer = optim.Adam(encoder.parameters(), lr=hparams["lr"])
    decoder_optimizer = optim.Adam(decoder.parameters(), lr=hparams["lr"])
    criterion = nn.NLLLoss()
    train_or_test(attention_change=True)
    train_or_test(True, attention_change=True)

# """## Experiment 2"""

# if __name__ == "__main__":
#     hparams = {
#         "batch_size": 32,
#         "hidden_size": 100,
#         "n_epochs": 4000,
#         "n_layers": 1,
#         "lr": 0.001,
#         "dropout": 0.1,
#         "print_every": 100,
#         "plot_every": 100,
#         "save_every": 100,
#         "eval_every": 1000,
#     }
#     experiment = "length_split"
#     train_data = read_file(f"{experiment}/tasks_train_length.txt")
#     test_data = read_file(f"{experiment}/tasks_test_length.txt")
#     # load langs with train and test data, so both have all the words from their respective domains
#     input_lang, output_lang, train_pairs, test_pairs = load_langs(
#         input_lang_name="primitives",
#         output_lang_name="commands",
#         train_data=train_data,
#         test_data=test_data,
#     )

#     max_length = get_max_length(train_pairs)

#     train_dataloader = get_dataloader(
#         batch_size=hparams["batch_size"],
#         max_length=max_length,
#         input_lang=input_lang,
#         output_lang=output_lang,
#         pairs=train_pairs,
#     )

#     test_dataloader = get_dataloader(
#         batch_size=hparams["batch_size"],
#         max_length=max_length,
#         input_lang=input_lang,
#         output_lang=output_lang,
#         pairs=test_pairs,
#     )

#     encoder = CommandEncoder(
#         input_size=input_lang.n_words,
#         hidden_size=hparams["hidden_size"],
#         n_layers=hparams["n_layers"],
#         dropout=hparams["dropout"],
#         device=device,
#     )
#     # encoder.load(f"models/{experiment}/encoder_500.pt")
#     decoder = ActionDecoder(
#         output_size=output_lang.n_words,
#         hidden_size=hparams["hidden_size"],
#         n_layers=hparams["n_layers"],
#         dropout=hparams["dropout"],
#         attention=True,
#         attention_type="luong",
#         device=device,
#     )
#     # decoder.load(f"models/{experiment}/decoder_500.pt")

#     encoder_optimizer = optim.Adam(encoder.parameters(), lr=hparams["lr"])
#     decoder_optimizer = optim.Adam(decoder.parameters(), lr=hparams["lr"])
#     criterion = nn.NLLLoss()
#     train_or_test(attention_change=True)
#     train_or_test(True, attention_change=True)

# """## Experiment 3"""

# if __name__ == "__main__":
#     hparams = {
#         "batch_size": 32,
#         "hidden_size": 100,
#         "n_epochs": 4000,
#         "n_layers": 1,
#         "lr": 0.001,
#         "dropout": 0.1,
#         "print_every": 10,
#         "plot_every": 100,
#         "save_every": 10,
#         "eval_every": 1000,
#     }
#     experiment = "add_prim_split"
#     variant = "turn_left"
#     # for variant in ['jump', 'turn_left']:
#     train_data = read_file(f"{experiment}/tasks_train_addprim_{variant}.txt")
#     test_data = read_file(f"{experiment}/tasks_test_addprim_{variant}.txt")
#     # load langs with train and test data, so both have all the words from their respective domains
#     input_lang, output_lang, train_pairs, test_pairs = load_langs(
#         input_lang_name="primitives",
#         output_lang_name="commands",
#         train_data=train_data,
#         test_data=test_data,
#     )

#     max_length = get_max_length(train_pairs)

#     train_dataloader = get_dataloader(
#         batch_size=hparams["batch_size"],
#         max_length=max_length,
#         input_lang=input_lang,
#         output_lang=output_lang,
#         pairs=train_pairs,
#     )

#     test_dataloader = get_dataloader(
#         batch_size=hparams["batch_size"],
#         max_length=max_length,
#         input_lang=input_lang,
#         output_lang=output_lang,
#         pairs=test_pairs,
#     )

#     encoder = CommandEncoder(
#         input_size=input_lang.n_words,
#         hidden_size=hparams["hidden_size"],
#         n_layers=hparams["n_layers"],
#         dropout=hparams["dropout"],
#         device=device,
#     )
#     encoder.load(f"models/{experiment}/{variant}_encoder_4000.pt")
#     decoder = ActionDecoder(
#         output_size=output_lang.n_words,
#         hidden_size=hparams["hidden_size"],
#         n_layers=hparams["n_layers"],
#         dropout=hparams["dropout"],
#         attention=True,
#         attention_type="bahdanau",
#         device=device,
#     )
#     decoder.load(f"models/{experiment}/{variant}_decoder_4000.pt")

#     encoder_optimizer = optim.Adam(encoder.parameters(), lr=hparams["lr"])
#     decoder_optimizer = optim.Adam(decoder.parameters(), lr=hparams["lr"])
#     criterion = nn.NLLLoss()

#     train_or_test(variant=variant)
#     train_or_test(testing=True, variant=variant)

# """## Experiment 4"""

# if __name__ == "__main__":
#     hparams = {
#         "batch_size": 32,
#         "hidden_size": 100,
#         "n_epochs": 4000,
#         "n_layers": 1,
#         "lr": 0.001,
#         "dropout": 0.1,
#         "print_every": 100,
#         "plot_every": 100,
#         "save_every": 100,
#         "eval_every": 1000,
#     }
#     experiment = "filler_split"
#     for variant in range(1, 4):
#         train_data = read_file(f"{experiment}/tasks_train_filler_num{variant}.txt")
#         test_data = read_file(f"{experiment}/tasks_test_filler_num{variant}.txt")
#         # load langs with train and test data, so both have all the words from their respective domains
#         input_lang, output_lang, train_pairs, test_pairs = load_langs(
#             input_lang_name="primitives",
#             output_lang_name="commands",
#             train_data=train_data,
#             test_data=test_data,
#         )

#         max_length = get_max_length(train_pairs)

#         train_dataloader = get_dataloader(
#             batch_size=hparams["batch_size"],
#             max_length=max_length,
#             input_lang=input_lang,
#             output_lang=output_lang,
#             pairs=train_pairs,
#         )

#         test_dataloader = get_dataloader(
#             batch_size=hparams["batch_size"],
#             max_length=max_length,
#             input_lang=input_lang,
#             output_lang=output_lang,
#             pairs=test_pairs,
#         )

#         encoder = CommandEncoder(
#             input_size=input_lang.n_words,
#             hidden_size=hparams["hidden_size"],
#             n_layers=hparams["n_layers"],
#             dropout=hparams["dropout"],
#             device=device,
#         )
#         # encoder.load(f"models/{experiment}/encoder_4000.pt")
#         decoder = ActionDecoder(
#             output_size=output_lang.n_words,
#             hidden_size=hparams["hidden_size"],
#             n_layers=hparams["n_layers"],
#             dropout=hparams["dropout"],
#             attention=True,
#             attention_type="bahdanau",
#             device=device,
#         )
#         # decoder.load(f"models/{experiment}/decoder_4000.pt")

#         encoder_optimizer = optim.Adam(encoder.parameters(), lr=hparams["lr"])
#         decoder_optimizer = optim.Adam(decoder.parameters(), lr=hparams["lr"])
#         criterion = nn.NLLLoss()
#         train_or_test(variant=variant)
#         hparams["print_every"] = 10
#         hparams["save_every"] = 10
#         train_or_test(testing=True, variant=variant)


# def generate_pretty_plot(x, y, xlabel, ylabel, title):
#     # Create figure and axes
#     fig, ax = plt.subplots()

#     # Plot the data
#     ax.plot(x, y, marker="o", linestyle="-", color="b")

#     # Set labels and title
#     ax.set_xlabel(xlabel)
#     ax.set_ylabel(ylabel)
#     ax.set_title(title)

#     # Customize tick marks
#     ax.tick_params(axis="both", which="both", direction="in", top=True, right=True)

#     # Add grid lines
#     ax.grid(True, linestyle="--", linewidth=0.5)

#     # Remove spines
#     ax.spines["top"].set_visible(False)
#     ax.spines["right"].set_visible(False)

#     # Show the plot
#     plt.show()
