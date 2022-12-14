# -*- coding: utf-8 -*-
"""pytorch_korbert_NSMC.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1YOHbYcGpmF6BDZzTgS3ZGp-Y6UMidkhH
"""

from google.colab import drive
drive.mount('/content/drive')

!nvidia-smi

"""형태소 분석기 Mecab 로드"""

!pip install -v python-mecab-ko

!pip install transformers
!pip install sentencepiece
!pip install pytorch-pretrained-bert
!pip install jamo
!pip install scikit-learn

cp /content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/src_tokenizer/tokenization_morp.py  /usr/local/lib/python3.7/dist-packages/pytorch_pretrained_bert/tokenization_morp.py

cp /content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/src_tokenizer/tokenization_morp.py  /usr/local/lib/python3.7/dist-packages/transformers/tokenization_morp.py

import urllib.request
import pandas as pd
import mecab
import numpy as np
import matplotlib.pyplot as plt
from torchtext import data # torchtext.data 임포트
import torch
import random

from transformers import BertPreTrainedModel, AdamW, BertConfig, BertModel, BertForSequenceClassification
from transformers import get_linear_schedule_with_warmup
from transformers import EvalPrediction
from pytorch_pretrained_bert.tokenization_morp import *
from sklearn.model_selection import train_test_split

from torch.utils.data import (DataLoader, RandomSampler, SequentialSampler,TensorDataset)
from torch.utils.data.distributed import DistributedSampler
from keras.preprocessing.sequence import pad_sequences
import torch.nn as nn

from torchsummary import summary
import torchvision
import re
from jamo import h2j, j2hcj
import time
import datetime
from tqdm import tqdm
import os
from collections import Counter

"""GPU 사용을 위한 코드"""

USE_CUDA = torch.cuda.is_available() # GPU를 사용가능하면 True, 아니라면 False를 리턴
device = torch.device("cuda" if USE_CUDA else "cpu") # GPU 사용 가능하면 사용하고 아니면 CPU 사용
print("다음 기기로 학습:", device)

# for reproducibility
random.seed(777)
torch.manual_seed(777)
if device == 'cuda':
    torch.cuda.manual_seed_all(777)

"""하이퍼파라미터 정의, 모델 세팅"""

# hyperparameters
num_train_epochs = 5
batch_size = 256
max_query_length = 128
learning_rate = 3e-5
warmup_proportion = 0.1 #Proportion of training to perform linear learning rate warmup for. E.g., 0.1 = 10%
num_warmup_steps = 10
gradient_accumulation_steps = 1 #Number of updates steps to accumulate before performing a backward/update pass


OUTPUT_DIR ='/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/finetuned_model/'


config = BertConfig.from_pretrained('/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/bert_config.json')

vocab_path = '/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/vocab.korean_morp.list'
tokenizer = BertTokenizer.from_pretrained(vocab_path, do_lower_case=False)

# state_dict = torch.load('/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/pytorch_model.bin')

# print(tokenizer.tokenize('테이퍼링 언급에 소폭 하락한 코스피…"차량용 반도체 회복은 4분기쯤"'))
# print(mecab.MeCab().parse('테이퍼링 언급에 소폭 하락한 코스피…"차량용 반도체 회복은 4분기쯤"'))
# print(mecab.MeCab().parse('테이퍼링'))
# tokenized = tokenizing(['테이퍼링 언급에 소폭 하락한 코스피…"차량용 반도체 회복은 4분기쯤"'])

# tokenized_sum = np.array(tokenized).flatten()

# total = ''
# for token in tokenized_sum:
#   total += token

# print(total)

# print(tokenizer.tokenize(total))

"""Mecab 품사 태그 --> 세종 품사 태그 변환(KorBERT에 맞도록)"""

SS_POS = ['"', "'"]
SW_POS = ['@','#', '$', '%', '^', '&', '*', '_', '+', '=', '`']
SO_POS = ['~', '-']

def convert_tag(pos, text):
  if pos == 'SF': return pos
  elif pos == 'SC': return 'SP'
  elif pos == 'NNBC': return 'NNB'
  elif pos == 'SSO' or pos == 'SSC' : return 'SS'
  elif text in SS_POS: return 'SS'
  elif text in SW_POS: return 'SW'
  elif text in SO_POS: return 'SO'
  elif pos == 'SY' : return 'SW'
  elif pos == 'UN' : return 'UNK'

  return pos

"""데이터 전처리 및 토크나이징 함수 정의"""

def tokenizing(data):

  pos_pat = re.compile('pos=[\']([^\),]*)[\']')
  exp_pat = re.compile('expression=[\']?([^\)\']*)[\']?')
  exp_pat2 = re.compile('([^\/+*]+[\/][^\/]+)')

  # 불용어 정의
  stopwords=['의','가','이','은','들','는','좀','잘','걍','과','도','를','으로','자','에','와','한','하다']
  tokenizer_morp = mecab.MeCab()
  tokenized=[]
  for sentence in tqdm(data):
      line = []
      temp = tokenizer_morp.parse(sentence) # 토큰화
      for text, feature in temp:
        pos = pos_pat.search(str(feature)).group(1)
        pos = convert_tag(pos, text)
        exp = exp_pat.search(str(feature)).group(1)

        if(exp != 'None'):
            exp_split = exp_pat2.findall(str(exp))
            for split_token in exp_split:
              line.append(j2hcj(split_token)+'_') # 종성 자모를 초성 자모로 바꾸기 위해 j2hcj 사용
        else:
          line.append(text+'/'+pos+'_')
      
      tokenized.append(line)
  return tokenized

"""정수 인코딩, 마스크, 패딩, 세그먼트 생성 함수 정의"""

def convert_to_ids_padding(tokenized):

  encoded = {'input_ids' : [],
            'attention_mask' : [],
            'position_ids' : [],
            'segment_ids' : []}

  for tokens in tokenized:
    temp_input_ids = []
    temp_attention_mask = []
    temp_position_ids = []
    temp_segment_ids = []


  # convert token to ids
    temp_input_ids.append(tokenizer.vocab['[CLS]'])
    for token in tokens:
      try:
        temp_input_ids.append(tokenizer.vocab[token])
      except KeyError:
        temp_input_ids.append(tokenizer.vocab['[UNK]'])
      
      if len(temp_input_ids) == MAX_LEN - 1:
        break

    temp_input_ids.append(tokenizer.vocab['[SEP]'])

  # attention_mask, segment_ids generation
    temp_attention_mask = [1]*len(temp_input_ids)
    temp_segment_ids = [0]*MAX_LEN
    
  # zero-padding
    while len(temp_input_ids) < MAX_LEN:
      temp_input_ids.append(0)
      temp_attention_mask.append(0)

    encoded['input_ids'].append(temp_input_ids)
    encoded['attention_mask'].append(temp_attention_mask)
    encoded['segment_ids'].append(temp_segment_ids)

  return encoded

"""데이터 로드"""

# urllib.request.urlretrieve("https://raw.githubusercontent.com/e9t/nsmc/master/ratings.txt", filename="ratings.txt")
# data = pd.read_table('ratings.txt') # 데이터프레임에 저장
# data.dropna(inplace = True)

# x_data = data['document']
# y_data = data['label']
data = pd.read_csv('/content/drive/MyDrive/data/disc_stock_merge_2021_05_19_timemod_add_corp_cleartext_ver.csv').dropna()

data['title'] = data['title'].str.replace("[.,ㆍ´]", "")

for idx in tqdm(data.index):
  hflunc = data.loc[idx, 'hflunc']
  
  if hflunc > 2.5: data.loc[idx, 'label'] = 1
  else: data.loc[idx, 'label'] = 0

x_data = data['title']
y_data = data['label']

x_train, x_test, y_train, y_test = train_test_split(x_data, y_data, test_size = 0.2, shuffle = True, stratify = y_data, random_state = 42)
x_train, x_valid, y_train, y_valid = train_test_split(x_train, y_train, test_size = 0.1, shuffle = True, stratify = y_train, random_state = 42)

print(x_data.head())
print(y_data.head())

data.groupby('label').size()

tokenized2 = tokenizing(data['title'])

flat_tokens = np.hstack(token for token in tokenized2)
count = Counter(flat_tokens)

print(len(count.most_common()))

f = open('/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/vocab.korean_morp.list', 'a')

for item in count.most_common(3000):
  try:
    print(item[0], tokenizer.vocab[item[0]], item[1])
  except KeyError:
    print(item[0], "--------UNKNOWN TOKEN--------")

# tokenized = tokenizing(data['document'])
tokenized = tokenizing(data['title'])

max_len = max(len(tokens) for tokens in tokenized)
mean_len = round(sum(map(len, tokenized))/len(tokenized))
print('리뷰의 최대 길이 : %d' % max_len)
print('리뷰의 최소 길이 : %d' % min(len(tokens) for tokens in tokenized))
print('리뷰의 평균 길이 : %f' % (sum(map(len, tokenized))/len(tokenized)))
plt.hist([len(tokens) for tokens in tokenized], bins=50)
plt.xlabel('length of sample')
plt.ylabel('number of sample')
plt.show()

MAX_LEN = mean_len + 5
print('MAX_LEN = {}'.format(MAX_LEN))

"""모델 클래스 정의 (Multi-Label Classification에 맞도록)"""

class BertForMultiLabelSequenceClassification(BertPreTrainedModel):
    """BERT model for classification.
    This module is composed of the BERT model with a linear layer on top of
    the pooled output.
    """
    def __init__(self, config, num_labels=2):
        super(BertForMultiLabelSequenceClassification, self).__init__(config)
        self.num_labels = num_labels
        self.bert = BertModel.from_pretrained('/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch',
                                              config = '/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/bert_config.json')
        self.dropout = torch.nn.Dropout(config.hidden_dropout_prob)
        self.classifier = torch.nn.Linear(config.hidden_size, num_labels)

    def forward(
        self,
        input_ids=None,
        attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        head_mask=None,
        inputs_embeds=None,
        labels=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
    ):
        return_dict = return_dict if return_dict is not None else self.config.use_return_dict

        outputs = self.bert(input_ids, token_type_ids, attention_mask)
        pooled_output = self.dropout(outputs[1])
        logits = self.classifier(pooled_output) # batch_size가 16이고 num_label이 2이므로 (16, 2) 사이즈의 텐서가 출력

        # training 할 때는 loss를 반환, evaluate 시에는 logits을 반환
        loss = None
        if labels is not None:
            if self.num_labels == 1:
                #  We are doing regression
                loss_fct = nn.MSELoss()
                loss = loss_fct(logits.view(-1), labels.view(-1))
            else:
                loss_fct = nn.CrossEntropyLoss() # 내부적으로 소프트맥스 함수 포함
                loss = loss_fct(logits.view(-1, self.num_labels), labels.view(-1))
                # loss = loss_fct(logits, labels)

        if not return_dict:
            output = (logits,) + outputs[2:]
            return ((loss,) + output) if loss is not None else output

        return SequenceClassifierOutput(
            loss=loss,
            logits=logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )
        
    def freeze_bert_encoder(self):
        for param in self.bert.parameters():
            param.requires_grad = False
    
    def unfreeze_bert_encoder(self):
        for param in self.bert.parameters():
            param.requires_grad = True

# model = BertForMultiLabelSequenceClassification(config)
model = BertForSequenceClassification.from_pretrained('/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch',
                                              config = '/content/drive/MyDrive/1_bert_download_001_bert_morp_pytorch/001_bert_morp_pytorch/bert_config.json')
model.to(device)

"""Optimizer 세팅"""

param_optimizer = list(model.named_parameters()) # 모델의 파라미터

param_optimizer = [n for n in param_optimizer if 'pooler' not in n[0]]

no_decay = ['bias', 'LayerNorm.bias', 'LayerNorm.weight']
optimizer_grouped_parameters = [
  {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)], 'weight_decay': 0.01},
  {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
  ]

"""모델 학습을 위해 input data를 tensordata로 만듦 (input data 세팅)"""

train_tokenized = tokenizing(x_train)
train_encoded = convert_to_ids_padding(train_tokenized)
valid_tokenized = tokenizing(x_valid)
valid_encoded = convert_to_ids_padding(valid_tokenized)
test_tokenized = tokenizing(x_test)
test_encoded = convert_to_ids_padding(test_tokenized)

print(len(train_encoded['input_ids']))
print(len(train_encoded['attention_mask']))
print(len(train_encoded['segment_ids']))
print(len(y_train))
train_input_ids = torch.tensor([f for f in train_encoded['input_ids']], dtype=torch.long)
train_input_mask = torch.tensor([f for f in train_encoded['attention_mask']], dtype=torch.long)
train_segment_ids = torch.tensor([f for f in train_encoded['segment_ids']], dtype=torch.long)
train_labels = torch.tensor([f for f in y_train], dtype=torch.long)

train_data = TensorDataset(train_input_ids, train_input_mask, train_segment_ids, train_labels)
train_sampler = RandomSampler(train_data)
train_dataloader = DataLoader(train_data, sampler=train_sampler, batch_size=batch_size)

valid_input_ids = torch.tensor([f for f in valid_encoded['input_ids']], dtype=torch.long)
valid_input_mask = torch.tensor([f for f in valid_encoded['attention_mask']], dtype=torch.long)
valid_segment_ids = torch.tensor([f for f in valid_encoded['segment_ids']], dtype=torch.long)
valid_labels = torch.tensor([f for f in y_valid], dtype=torch.long)

valid_data = TensorDataset(valid_input_ids, valid_input_mask, valid_segment_ids, valid_labels)
valid_sampler = RandomSampler(valid_data)
valid_dataloader = DataLoader(valid_data, sampler=valid_sampler, batch_size=batch_size)

test_input_ids = torch.tensor([f for f in test_encoded['input_ids']], dtype=torch.long)
test_input_mask = torch.tensor([f for f in test_encoded['attention_mask']], dtype=torch.long)
test_segment_ids = torch.tensor([f for f in test_encoded['segment_ids']], dtype=torch.long)
test_labels = torch.tensor([f for f in y_test], dtype=torch.long)

test_data = TensorDataset(test_input_ids, test_input_mask, test_segment_ids, test_labels)
test_sampler = RandomSampler(test_data)
test_dataloader = DataLoader(test_data, sampler=test_sampler, batch_size=batch_size)

train_encoded['input_ids'][:10]

# num_train_steps = int(len(x_train) / batch_size / gradient_accumulation_steps * num_train_epochs)
num_train_steps = len(train_dataloader) * num_train_epochs
t_total = num_train_steps

optimizer = AdamW(optimizer_grouped_parameters, lr=learning_rate, correct_bias=False)  # To reproduce BertAdam specific behavior set correct_bias=False
scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=num_warmup_steps, num_training_steps=num_train_steps)  # PyTorch scheduler

"""Accuracy와 시간 표시 함수 정의"""

# 정확도 계산 함수
def flat_accuracy(preds, labels):
    pred_flat = np.argmax(preds, axis=1).flatten()
    labels_flat = labels.flatten()
    return np.sum(pred_flat == labels_flat) / len(labels_flat)

# 시간 표시 함수
def format_time(elapsed):
    # 반올림
    elapsed_rounded = int(round((elapsed)))
    # hh:mm:ss으로 형태 변경
    return str(datetime.timedelta(seconds=elapsed_rounded))

#그래디언트 초기화
model.zero_grad()

for epoch in range(0, num_train_epochs):

    # ========================================
    #               Training
    # ========================================
    
  print("")
  print('======== Epoch {:} / {:} ========'.format(epoch + 1, num_train_epochs))
  print('Training...')

  t0 = time.time()

  # 로스 초기화
  total_loss = 0

  model.train()

  for step, batch in enumerate(train_dataloader):
    
    #경과 정보 표시
    if step % 500 == 0 and not step == 0:
        elapsed = format_time(time.time() - t0)
        print('  Batch {:>5,}  of  {:>5,}.    Elapsed: {:}.'.format(step, len(train_dataloader), elapsed))

    batch = tuple(t.to(device) for t in batch)
    input_ids, attention_mask, segment_ids, labels = batch

    #forward 수행
    outputs = model(input_ids = input_ids, 
                    token_type_ids = segment_ids, 
                    attention_mask = attention_mask, 
                    labels = labels, 
                    return_dict = False)
    loss = outputs[0]
    
    total_loss += loss.item()
    
    # Backward 수행으로 그래디언트 계산
    loss.backward()

    optimizer.step()
    scheduler.step()
    optimizer.zero_grad()

    # print('Elapsed Time : {}'.format(time.time()-start_time))

  # 평균 로스 계산
  avg_train_loss = total_loss / len(train_dataloader)            

  print("")
  print("  Average training loss: {0:.2f}".format(avg_train_loss))
  print("  Training epcoh took: {:}".format(format_time(time.time() - t0)))

  # ========================================
  #               Validation
  # ========================================

  print("")
  print("Running Validation...")

  #시작 시간 설정
  t0 = time.time()

  # 평가모드로 변경
  model.eval()

  # 변수 초기화
  eval_loss, eval_accuracy = 0, 0
  nb_eval_steps, nb_eval_examples = 0, 0

  # 데이터로더에서 배치만큼 반복하여 가져옴
  for batch in valid_dataloader:
    # 배치를 GPU에 넣음
    batch = tuple(t.to(device) for t in batch)
    
    # 배치에서 데이터 추출
    b_input_ids, b_attention_mask, b_segment_ids, b_labels = batch
    
    # 그래디언트 계산 안함
    with torch.no_grad():     
        # Forward 수행
        outputs = model(b_input_ids, 
                        token_type_ids= b_segment_ids, 
                        attention_mask=b_attention_mask,
                        return_dict = False)
    
    # 로스 구함
    logits = outputs[0]

    # CPU로 데이터 이동
    logits = logits.detach().cpu().numpy()
    label_ids = b_labels.to('cpu').numpy()
    
    # 출력 로짓과 라벨을 비교하여 정확도 계산
    tmp_eval_accuracy = flat_accuracy(logits, label_ids)
    eval_accuracy += tmp_eval_accuracy
    nb_eval_steps += 1

  print("  Accuracy: {0:.2f}".format(eval_accuracy/nb_eval_steps))
  print("  Validation took: {:}".format(format_time(time.time() - t0)))

print("")
print("Training complete!")

"""모델 저장"""

# 모델 저장
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

model_to_save = model.module if hasattr(model, 'module') else model
model_to_save.save_pretrained(OUTPUT_DIR)

"""테스트"""

#시작 시간 설정
t0 = time.time()

# 평가모드로 변경
model.eval()

# 변수 초기화
eval_loss, eval_accuracy = 0, 0
nb_eval_steps, nb_eval_examples = 0, 0

# 데이터로더에서 배치만큼 반복하여 가져옴
for step, batch in enumerate(test_dataloader):
    # 경과 정보 표시
    if step % 100 == 0 and not step == 0:
        elapsed = format_time(time.time() - t0)
        print('  Batch {:>5,}  of  {:>5,}.    Elapsed: {:}.'.format(step, len(test_dataloader), elapsed))

    # 배치를 GPU에 넣음
    batch = tuple(t.to(device) for t in batch)
    
    # 배치에서 데이터 추출
    b_input_ids, b_attention_mask, b_segment_ids, b_labels = batch
    
    # 그래디언트 계산 안함
    with torch.no_grad():     
        # Forward 수행
        outputs = model(b_input_ids, 
                        token_type_ids=b_segment_ids, 
                        attention_mask=b_attention_mask,
                        return_dict = False)
    
    # 로스 구함
    logits = outputs[0]

    # CPU로 데이터 이동
    logits = logits.detach().cpu().numpy()
    label_ids = b_labels.to('cpu').numpy()

    
    # 출력 로짓과 라벨을 비교하여 정확도 계산
    tmp_eval_accuracy = flat_accuracy(logits, label_ids)
    eval_accuracy += tmp_eval_accuracy
    nb_eval_steps += 1

print("")
print("Accuracy: {0:.2f}".format(eval_accuracy/nb_eval_steps))
print("Test took: {:}".format(format_time(time.time() - t0)))

def predict(text, model):
  text_tokenized = tokenizing([text])
  print(text_tokenized)
  text_encoded = convert_to_ids_padding(text_tokenized)

  input_ids = torch.tensor(text_encoded['input_ids'], dtype=torch.long).to(device)
  attention_mask = torch.tensor(text_encoded['attention_mask'], dtype=torch.long).to(device)
  segment_ids = torch.tensor(text_encoded['segment_ids'], dtype=torch.long).to(device)

  print([text_encoded['input_ids']])
  # 그래디언트 계산 안함
  with torch.no_grad():     
      # Forward 수행
      outputs = model(input_ids, 
                      token_type_ids=segment_ids, 
                      attention_mask=attention_mask,
                      return_dict = False)
      
  logits = outputs[0]
  result = torch.nn.functional.softmax(logits).to('cpu') # 'cuda'에 attach 되어있을 때는 np.array로 변환 불가. cpu로 붙어줘야 함
  max = np.argmax(result)
  return (max, result)

predict('현대건설, 1조1900억 규모 복합시설 신축공사 수주', model)

"""vocabulary 정의

패딩을 위한 텍스트 길이 추출

패딩
"""