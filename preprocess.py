import os
import re
import numpy as np
import pandas as pd
from collections import namedtuple

from keras.preprocessing import text, sequence
from keras.utils import to_categorical


FILE_PATH = os.path.dirname(os.path.realpath(__file__))
DATA_PATH = os.path.join(FILE_PATH, 'data')

MODE_DATAFILES = {
    'cb513'     : {'train': 'cb6133filtered.npy', 'test': 'cb513.npy'},
    'weightq8'  : {'train': 'train_Q8_data.txt', 'test': 'test_Q8_data.txt'},
    'weightq13' : {'train': 'train_Q13_data.txt', 'test': 'test_Q13_data.txt'}
}

RESIDUES = ['A', 'C', 'E', 'D', 'G', 'F', 'I', 'H', 'K', 'M', 'L', 'N', 'Q', 'P', 'S', 'R', 'T', 'W', 'V', 'Y', 'X','NoSeq']
Q8_STRUCTURES = ['L', 'B', 'E', 'G', 'I', 'H', 'S', 'T','NoSeq']

DataSplit = namedtuple('DataSplit', ['seq_df', 'profile', 'sequence', 'labels'])


class DataPreprocessor:
    def __init__(self, mode, maxlen_seq):
        self.mode = mode
        self.maxlen_seq = maxlen_seq
        self.input_tokenizer = text.Tokenizer(char_level=True)
        self.target_tokenizer = text.Tokenizer(char_level=True)
        self.dataset_split = dict()

        self.preprocess()

    @property
    def train_test_files(self):
        return MODE_DATAFILES[self.mode]

    @property
    def input_token_map(self):
        return dict((v, k) for k, v in self.input_tokenizer.word_index.items())

    @property
    def target_token_map(self):
        return dict((v, k) for k, v in self.target_tokenizer.word_index.items())

    @property
    def num_words(self):
        return len(self.input_tokenizer.word_index) + 1

    @property
    def num_labels(self):
        return len(self.target_tokenizer.word_index) + 1
    
    def get_train_data(self):
        return self.dataset_split.get('train')

    def get_test_data(self):
        return self.dataset_split.get('test')

    def preprocess(self):
        load_func = 'load_cb513_data' if self.mode == 'cb513' else 'load_pdb_weight_data'

        for split_type in ['train', 'test']:
            # TODO: Write these to a file to not have to parse every time
            seq_df, profile = getattr(self, load_func)(self.train_test_files[split_type], self.maxlen_seq)
            tokenizer_input_df = seq_df[seq_df['input'].map(len) <= self.maxlen_seq]
            inputs, targets = tokenizer_input_df.values.T

            if split_type == 'train':
                self.input_tokenizer.fit_on_texts(inputs)
                self.target_tokenizer.fit_on_texts(targets)

            input_data = self.input_tokenizer.texts_to_sequences(inputs)
            x = sequence.pad_sequences(input_data, maxlen=self.maxlen_seq, padding='post')
            target_data = self.target_tokenizer.texts_to_sequences(targets)
            target_data = sequence.pad_sequences(target_data, maxlen=self.maxlen_seq, padding='post')
            y = to_categorical(target_data)
            self.dataset_split[split_type] = DataSplit(seq_df=tokenizer_input_df,
                                                       profile=profile,
                                                       sequence=x,
                                                       labels=y)
    
    @staticmethod
    def load_cb513_data(filename, max_len):
        filepath = os.path.join(DATA_PATH, filename)
        data = np.load(filepath)

        data_reshape = data.reshape(data.shape[0], 700, -1)
        seq_onehot = data_reshape[:,:,0:22]
        q8_onehot = data_reshape[:,:,22:31]
        profile = data_reshape[:,:,35:57]

        zero_arr = np.zeros((profile.shape[0], max_len - profile.shape[1], profile.shape[2]))
        profile_padded = np.concatenate([profile, zero_arr], axis=1)
        seq_array = np.array(RESIDUES)[seq_onehot.argmax(2)]
        q8_array = np.array(Q8_STRUCTURES)[q8_onehot.argmax(2)]
        seq_str_list = [''.join(vec[vec != 'NoSeq']) for vec in seq_array]
        q8_str_list = [''.join(vec[vec != 'NoSeq'] )for vec in q8_array]

        train_df = pd.DataFrame({'input': seq_str_list, 'expected': q8_str_list})
        return train_df, profile_padded

    @staticmethod
    def load_pdb_weight_data(filename, max_len):
        filepath = os.path.join(DATA_PATH, filename)
        residue_array, q13_array, pssm_big = list(), list(), list()

        with open(filepath, 'r') as f_in:
            for line in f_in:
                # Data has '-' interspersed within sequence
                # Need to read in blanks to know which rows to remove from pssm before padding
                seq, ss_seq, pssm = line.strip().split('|')

                padded_seq_pssm = np.zeros((max_len, 22))
                pssm_arr = np.reshape(np.fromstring(pssm, dtype=int, sep=' '), (len(seq), 22))
                empties = [x.start() for x in re.finditer('-', seq)]
                pssm_arr = np.delete(pssm_arr, empties, 0)  # delete rows
                padded_seq_pssm[:pssm_arr.shape[0], :pssm_arr.shape[1]] = pssm_arr
                pssm_big.append(padded_seq_pssm)

                seq = seq.replace('-', '')
                ss_seq = ss_seq.replace('-', '')

                residue_array.append(list(seq + '-'*(max_len - len(seq))))
                q13_array.append(list(ss_seq + '-'*(max_len - len(ss_seq))))

        profile_padded = np.stack(pssm_big)
        residue_array = np.array(residue_array)
        q13_array = np.array(q13_array)
        residue_str_list = [''.join(vec[vec != '-']) for vec in residue_array]
        q13_str_list = [''.join(vec[vec != '-']) for vec in q13_array]

        train_df = pd.DataFrame({'input': residue_str_list, 'expected': q13_str_list})

        return train_df, profile_padded
