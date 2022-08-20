# -*- coding: utf-8 -*-
"""KoElectra_Tensorflow_NSMC.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1dcyEhMu0uOlDQYzzNHLCvl7ss-tgX2O2
"""

from google.colab import drive
drive.mount('/content/drive')

!nvidia-smi

!pip install transformers
!pip install sentencepiece

from transformers import TFElectraModel, ElectraTokenizer, TFElectraPreTrainedModel, ElectraConfig, TFElectraForSequenceClassification

from tensorflow.keras import Model,models
from sklearn.model_selection import train_test_split
from tensorflow.keras.preprocessing.sequence import pad_sequences
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.losses import SparseCategoricalCrossentropy
from tensorflow.keras.metrics import SparseCategoricalAccuracy
from tensorflow.keras.layers import Softmax

import tensorflow as tf
import pandas as pd
import urllib
import matplotlib.pyplot as plt

import os
import re
import numpy as np
from tqdm import tqdm
# from konlpy.tag import Mecab

import requests
from datetime import datetime, timedelta, date
from bs4 import BeautifulSoup
from threading import Timer

BATCH_SIZE = 16
NUM_EPOCHS = 15
VALID_SPLIT = 0.2

tokenizer = ElectraTokenizer.from_pretrained("monologg/koelectra-base-v3-discriminator")

DATA_OUT_PATH = '/content/drive/MyDrive/Electra'

#==============================================================================================

# data = pd.read_csv('/content/drive/MyDrive/data/total_cleartext_polarity_labeled.csv').dropna()
# x_data = data['content']
# y_data = data['label']

#===============================================================================================

# data = pd.read_csv('/content/drive/MyDrive/data/disc_stock_merge_2021_05_19_timemod_add_corp_cleartext_ver.csv').dropna()

# for idx in tqdm(data.index):
#   hflunc = data.loc[idx, 'hflunc']
  
#   if hflunc > 2.5: data.loc[idx, 'label'] = 1
#   else: data.loc[idx, 'label'] = 0
  
# x_data = data['title']
# y_data = data['label']

#===============================================================================================
# data = pd.read_csv('/content/drive/MyDrive/data/stock_news_merge_cleartext_final2.csv', index_col = 0).dropna()
# neg_data = data[data['label'] == 0]
# pos_data = data[data['label'] == 1]
# neg_rand_sample = neg_data.sample(n=150000, random_state = 777)

# data = pd.concat([neg_rand_sample, pos_data], ignore_index=True)

# x_data = data['content']
# y_data = data['label']

#=========================================================================================================================
# data = pd.read_csv('/content/drive/MyDrive/data/기업_종목분석_cleartext_polarity_labeled2.csv', index_col = 0).dropna()
# x_data = data['content']
# y_data = data['label']

data = pd.read_csv('/content/drive/MyDrive/data/total_stock_labeling.csv')
x_data = data['content']
y_data = data['label']

x_train, x_test, y_train, y_test = train_test_split(x_data, y_data, test_size = 0.2, shuffle = True, stratify = y_data, random_state = 42)

data.groupby('label').size()

def get_maxlen():
  tokenized_list = [tokenizer.encode(sentence) for sentence in tqdm(x_data.values)]
  max_len = max(len(tokens) for tokens in tokenized_list)
  mean_len = round(sum(map(len, tokenized_list))/len(tokenized_list))
  print('리뷰의 최대 길이 : %d' % max_len)
  print('리뷰의 최소 길이 : %d' % min(len(tokens) for tokens in tokenized_list))
  print('리뷰의 평균 길이 : %f' % (sum(map(len, tokenized_list))/len(tokenized_list)))
  plt.hist([len(tokens) for tokens in tokenized_list], bins=50)
  plt.xlabel('length of sample')
  plt.ylabel('number of sample')
  plt.show()

  MAX_LEN = mean_len + 5
  print('MAX_LEN = {}'.format(MAX_LEN))
  return MAX_LEN

def bert_tokenizer(sent, MAX_LEN):
    pat = re.compile('[-.:\'\"=]')
    sent = pat.sub(" ", sent)
    sent = sent.strip()
    
    encoded_dict = tokenizer.encode_plus(
        text = sent,
        add_special_tokens = True, # Add '[CLS]' and '[SEP]'
        max_length = MAX_LEN,           # Pad & truncate all sentences.
        pad_to_max_length = True,
        return_attention_mask = True   # Construct attn. masks.
        
    )
    
    input_id = encoded_dict['input_ids']
    attention_mask = encoded_dict['attention_mask'] # And its attention mask (simply differentiates padding from non-padding).
    token_type_id = encoded_dict['token_type_ids'] # differentiate two sentences
    
    return input_id, attention_mask, token_type_id

input_id, attention_mask, token_type_id = bert_tokenizer('아이큐어는 식품의약품안전처로부터 도네페질 패취 의약품 품목허가 승인을 받았다고 3일 공시했다.', 50)
print(input_id)
print(attention_mask)
print(token_type_id)

MAX_LEN = get_maxlen()

MAX_LEN = 225

input_ids = []
attention_masks = []
token_type_ids = []
train_data_labels = []

for train_sent, train_label in tqdm(zip(x_train, y_train), total=len(x_train)):
    try:
        input_id, attention_mask, token_type_id = bert_tokenizer(train_sent, MAX_LEN)
        
        input_ids.append(input_id)
        attention_masks.append(attention_mask)
        token_type_ids.append(token_type_id)
        train_data_labels.append(train_label)

    except Exception as e:
        print(e)
        print(train_sent)
        pass

## 학습 데이터를 numpy array로 변환
train_input_ids = np.array(input_ids, dtype=int)
train_attention_masks = np.array(attention_masks, dtype=int)
train_type_ids = np.array(token_type_ids, dtype=int)
train_inputs = (train_input_ids, train_attention_masks, train_type_ids)

train_data_labels = np.asarray(train_data_labels, dtype=np.int32) #레이블 토크나이징 리스트

print("# sents: {}, # labels: {}".format(len(train_input_ids), len(train_data_labels)))

config = ElectraConfig.from_pretrained('monologg/koelectra-base-v3-discriminator')
cls_model = TFElectraForSequenceClassification.from_pretrained('monologg/koelectra-base-v3-discriminator', from_pt=True)
cls_model1 = TFElectraForSequenceClassification.from_pretrained('monologg/koelectra-base-v3-discriminator', from_pt=True)
cls_model2 = TFElectraForSequenceClassification.from_pretrained('monologg/koelectra-base-v3-discriminator', from_pt=True)

cls_model1.summary()
cls_model2.summary()

optimizer = tf.keras.optimizers.Adam(3e-5)
loss = tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True)
metric = tf.keras.metrics.SparseCategoricalAccuracy('accuracy')

cls_model.compile(optimizer=optimizer, loss=loss, metrics=[metric])  # 주가 등락 분류 모델
cls_model1.compile(optimizer=optimizer, loss=loss, metrics=[metric])  # 뉴스 긍/부정 분류 모델
cls_model2.compile(optimizer=optimizer, loss=loss, metrics=[metric])  # 뉴스 긍/부정 분류 모델

# model_name = "koelectra-tf-nsmc"
model_name = "koelectra-tf-stock_news_merge"

# overfitting을 막기 위한 ealrystop 추가
earlystop_callback = EarlyStopping(monitor='val_accuracy', min_delta=0.0001,patience=2)
# min_delta: the threshold that triggers the termination (acc should at least improve 0.0001)
# patience: no improvment epochs (patience = 1, 1번 이상 상승이 없으면 종료)

checkpoint_path = os.path.join(DATA_OUT_PATH, model_name, 'weights3.h5')
checkpoint_dir = os.path.dirname(checkpoint_path)

# Create path if exists
if os.path.exists(checkpoint_dir):
    print("{} -- Folder already exists \n".format(checkpoint_dir))
else:
    os.makedirs(checkpoint_dir, exist_ok=True)
    print("{} -- Folder create complete \n".format(checkpoint_dir))
    
cp_callback = ModelCheckpoint(
    checkpoint_path, monitor='val_accuracy', verbose=1, save_best_only=True, save_weights_only=True)

# 학습과 eval 시작
history = cls_model.fit(train_inputs, train_data_labels,
                        epochs=NUM_EPOCHS, batch_size=BATCH_SIZE,
                    validation_split = VALID_SPLIT, callbacks=[earlystop_callback, cp_callback])

#steps_for_epoch

print(history.history)

input_ids = []
attention_masks = []
token_type_ids = []
test_data_labels = []

for test_sent, test_label in tqdm(zip(x_test, y_test)):
    try:
        input_id, attention_mask, token_type_id = bert_tokenizer(test_sent, MAX_LEN)

        input_ids.append(input_id)
        attention_masks.append(attention_mask)
        token_type_ids.append(token_type_id)
        test_data_labels.append(test_label)
    except Exception as e:
        print(e)
        print(test_sent)
        pass

test_input_ids = np.array(input_ids, dtype=int)
test_attention_masks = np.array(attention_masks, dtype=int)
test_type_ids = np.array(token_type_ids, dtype=int)
test_inputs = (test_input_ids, test_attention_masks, test_type_ids)

test_data_labels = np.asarray(test_data_labels, dtype=np.int32) #레이블 토크나이징 리스트

print("num sents, labels {}, {}".format(len(test_input_ids), len(test_data_labels)))



cls_model1.load_weights('/content/drive/MyDrive/Electra/koelectra-tf-nsmc/weights.h5')
cls_model2.load_weights('/content/drive/MyDrive/Electra/koelectra-tf-stock_news_merge/weights2.h5')
cls_model.load_weights('/content/drive/MyDrive/Electra/koelectra-tf-stock_news_merge/weights3.h5')

results = cls_model.evaluate(test_inputs, test_data_labels, batch_size=256)
print("test loss, test acc: ", results)

def prediction(text_set):

  input_ids = []
  attention_masks = []
  token_type_ids = []

  for text in text_set:
    try:
      input_id, attention_mask, token_type_id = bert_tokenizer(text, MAX_LEN)

      input_ids.append(input_id)
      attention_masks.append(attention_mask)
      token_type_ids.append(token_type_id)
    except Exception as e:
        print(e)
        print(text)
        pass

  # train_input_ids.append(input_ids)로 리스트에 다시 batch의 input_ids를 넣을 때와 달리(학습시) 지금은 하나의 데이터만 사용하므로 리스트 안에 input_ids를 직접 넣어서 model의 인풋으로 넣어줘야함.
  input_ids = np.array(input_ids, dtype=int)
  attention_masks = np.array(attention_masks, dtype=int)
  token_type_ids = np.array(token_type_ids, dtype=int)

  encoded = {'input_ids' : input_ids, 'attention_masks':attention_masks,'token_type_ids':token_type_ids}
  inputs = (input_ids, attention_masks, token_type_ids)

  layer = Softmax()

  results1 = layer(cls_model1.predict(inputs)[0])  #긍/부정 분류 결과
  results2 = layer(cls_model2.predict(inputs)[0])  #주가 등락 여부 분류 결과
  results3 = layer(cls_model.predict(inputs)[0])


  for text, result1, result2, result3 in zip(text_set, results1, results2, results3):

    corp_name = extract_corpname(text)

    # arg = np.argmax(result1.numpy().flatten())
    # if arg == 0: pol = '부정'
    # else: pol = '긍정'
    # prob = np.round(result1.numpy().flatten()[arg]*100, 2)

    print('='*300)
    print(text)
    # print("{}% 확률로 {}적인 뉴스입니다. 해당하는 종목은 {} 입니다.".format(prob, pol, corp_name))

    arg = np.argmax(result2.numpy().flatten())
    if arg == 0: pol = '하락'
    else: pol = '상승'
    prob = np.round(result2.numpy().flatten()[arg]*100, 2)

    print("{}% 확률로 {}이 예상되는 뉴스입니다.".format(prob, pol, corp_name))

    arg = np.argmax(result3.numpy().flatten())
    if arg == 0: pol = '하락'
    else: pol = '상승'
    prob = np.round(result3.numpy().flatten()[arg]*100, 2)

    print("{}% 확률로 {}이 예상되는 뉴스입니다. 해당하는 종목은 {} 입니다.".format(prob, pol, corp_name))

text_set = [
    '현대자동차가 아산공장에서의 자동차 제조를 사흘간 중단한다고 24일 공시했다. 생산재개 예정일은 이달 27일이다. 회사 측은 생산 중단 사유에 대해 차량용 반도체 부품 수급 차질 때문이라고 밝혔다. ',
    'SK렌터카, 국내 여행 증가로 단기 렌터카 실적 호조-KTB',
    '한국거래소는 2020년도 12월 결산 한계기업 중 24개사에 대해 심리의뢰를 했다고 27일 밝혔다. 이날 거래소 시장감시위원회는 2020년도 12월 결산 한계기업 50개사의 불공정거래 혐의 여부 등에 대해 기획감시를 실시했다고 설명했다. 한계기업은 상장폐지 우려가 있거나 관리종목으로 지정된 기업, 감사의견 비적정을 받은 기업 등을 가리킨다.이 가운데 시감위는 24개사에서 불공정거래 관련 유의미한 혐의사항을 발견하고 추가 조사를 위한 심리의뢰를 했다. 코스피 6개사, 코스닥 18개사 등이며 유형별로는 미공개 중요정보이용 21건, 부정거래·시세조종 의심 사안 3건 등이다.한편 시감위가 이들 기업을 세부 분석한 결과 감사보고서 제출일 기준 1개월간 주가가 하락한 종목은 22개사에 달했다. 평균 하락률은 30.05%로, 이중 4개사는 50% 이상의 하락폭을 시현했다.',
    '이엔코퍼레이션 자회사 한성크린텍이 삼성전자 반도체 관련 수주가 이어지고 있다.한성크린텍은 삼성엔지니어링과 114억원 규모의 삼성전자 평택 P3 그린동 유틸리티 계약을 체결했다고 27일 밝혔다. P3 그린동은 P3 공장에서 발생되는 폐수처리 관련 시설이다.지난 20일 한성크린텍은 삼성물산으로부터 265억원 규모의 삼성전자 평택 P3 EUV동 PCW&GAS(Process Cooling Water & GAS) 및 HVAC(heating, ventilation, & air conditioning) DUCT 설비 작업지시서를 접수했다.2건의 삼성 반도체 관련 공사를 수주하는 데 성공했다. 수주규모는 379억원으로 지난해 한성크린텍 연간 매출액의 34% 규모다.',
    '현대자동차는 차량용 반도체 부품이 재공급됨에 따라 아산공장에서 자동차 제조를 재개한다고 27일 공시했다.생산재개 분야의 매출액은 7045억5470만원으로 최근 매출액 대비 6.77% 수준이다.앞서 아산공장은 지난 24일부터 26일까지 사흘간 자동차 약 3096대 생산을 중단한 바 있다.',
    '엑스레이 검사장비 전문업체인 자비스가 올해 1분기 연결기준 매출이 전년 동기 대비 5.72% 감소한 32억원을 기록했다고 27일 밝혔다. 같은 기간 영업손실은 11억원으로 적자를 지속했다.자비스 관계자는 "신종 코로나바이러스 감염증(코로나19)으로 매출에 타격이 있었다"며 "전문 인력 모집과 함께 연구 투자 비용을 늘리면서 이에 따른 영업손실이 발생됐다"고 설명했다.자비스의 제품기준 수주영업 실적은 전년 동기대비 23.4% 증가된 약 36억원을 달성했다. 검사장비 XSCAN 부문 중 전기자동차(EV) 배터리 제품 수주액은 지난해 대비 245% 상승했다.',
    '쿠팡 잭팟으로 ‘승부사’, ‘투자의 귀재’로 이름을 알린 손정의 소프트뱅크그룹 회장이 인공지능(AI) 업계로 눈길을 돌렸다.27일 금융투자업계에 따르면 지난 25일 손 회장이 이끄는 소프트뱅크 비전펀드2는 국내 AI 솔루션 스타트업 뤼이드를 대상으로 1억7500만달러(약 2000억원) 규모의 투자에 나섰다.소프트뱅크는 뤼이드의 대표 서비스 ‘산타토익’를 높이 평가해 투자를 결정했다. 이 서비스는 6~10문제 만으로 사용자 점수를 예측하고, 개인별 특성에 맞는 맞춤형 문제와 강의를 제공한다. 최단 학습 동선을 설계해 빠른 속도로 회원이 늘어나고 있는 추세다.시장에서는 이번 소프트뱅크의 대규모 투자가 글로벌 AI 업계 전반으로 확산될 가능성에 주목하고 있다. 손 회장은 올해 초부터 AI 산업부문 유망 기업들을 발굴해 전방위 투자에 나서겠다는 의지를 피력했다.국내 자본시장 업계도 유망 AI 기업 투자에 발 빠르게 대응하고 있다. 이번 소프트뱅크의 뤼이드 투자에 앞서 DSC인베스트먼트, IMM인베스트먼트 등 다수 벤처캐피탈(VC)들이 뤼이드에 대한 투자를 진행했다. 지난해 7월에는 산업은행도 투자에 나섰다.',
    '크레디트스위스(CS)는 이날 LG화학의 목표주가를 기존 130만원에서 68만원으로 대폭 낮췄다. 이는 현 주가 대비 18% 가량 낮은 수준이다. 투자의견 역시 아웃퍼폼(시장수익률 상회)에서 언더퍼폼(시장수익률 하회)으로 내렸다.CS는 투자의견과 목표주가를 하향 조정한 근거로 다른 지주사처럼 높은 할인율이 적용될 필요가 있기 때문이라고 설명했다.민훈식 CS 연구원은 LG화학에 대해 "커버리지 종목 중 가장 비선호하는 종목"이라고 적었다.이어 "LG에너지솔루션이 상장을 앞둔 시점에 투자자들이 큰 폭의 할인을 받을 수 있는 모회사를 살 이유가 없으며 (상장 이후) 지분율은 기존 100%에서 70%로 낮아질 것"이라고 말했다. CS는 지분 가치 희석과 지주사 할인을 피할 수 없다고 덧붙였다.',
    '금호건설은 전 경영진의 횡령 및 배임혐의에 따른 기소설에 대한 조회공시 요구에 "독점규제 및 공정거래에 관한 법률 위반 혐의로 기소됐음을 확인했고, 그 외 특정경제범죄가중처벌 등에 관한 법률위반(횡령 및 배임) 혐의에 대해서는 해당사항이 없음을 확인했다"고 26일 공시했다.',
    '셀리버리는 미국에서 개발중인 내재면역치료제 iCP-NI가 글로벌 위탁효능평가기관인 엠엘엠(MLM Medical Labs)의 효능평가에서 임상개발이 가능한 수준의 아토피 치료효능 증명에 성공했다고 26일 밝혔다.김재현 셀리버리 자가면역질환 개발책임자는 “최근 글로벌 신약효능평가기관인 엠엘엠으로부터 아토피피부염 효력시험 분석결과, 아토피 치료효능 평가지표인 아토피피부염 중증지수에서 60% 이상의 치료효능을 보였다"고 말했다.',
    '국내에서 코비박 사업을 총괄하고 있는 곳은 엠피코퍼레이션으로 지난 2월 코비박 백신의 국내 위탁 생산 및 아세안 국가 총판에 관한 양해각서(MOU)를 체결했다. 휴먼엔은 웨바이오텍과 엠피코퍼레이션에 각각 70억원 규모를 출자해 코비박 관련주로 분류되고 있다.',
    '앞서 LG에너지솔루션은 2017년 4월부터 2018년 9월까지 ESS 배터리 전용 생산라인에서 생산된 ESS용 배터리에 대해 자발적인 교체에 나선다고 밝혔다. 배터리 교체 및 추가 조치에 필요한 비용은 약 4000억원 수준으로 파악된다.',
    '유럽연합 집행위원회(EC)는 25일(현지시간) LG전자와 마그나의 합작사 설립을 승인했다. 앞서 LG전자는 지난 3월 주주총회에서 VS사업본부 내 전기차 파워트레인 사업을 물적 분할하는 안건을 의결했다. 이어 EC의 허가를 받으며 합작사 설립에 탄력이 붙었다.',
    '지난 2019년 10월 임상 3상 통계분석에서 유의성을 확보하지 못해 임상시험 설계를 보완한 뒤 현재 3상을 재추진하고 있다. 지난 6일 시험계획을 승인받기도 했다.배요한 강스템바이오텍 임상개발본부장은 "재추진하는 임상 3상에선 인력 보완을 통한 전문성 강화, 임상시험용 의약품의 세포기능 유지, 환자 중심의 임상시험 디자인 도입 등을 통해 성공 가능성을 높였다"고 말했다.',
    '진흥기업은 칸서스로지스틱스PFV로부터 250억원 규모의 경이 ㄴ아라뱃길 물류센터 신축공사를 수주했다고 27일 공시했다. 이는 지난해 개별 기준 매출액의 6.61%에 해당하는 규모다.',
    '현대자동차(005380)는 27일부로 아산공장 자동차 제조를 재개했다고 이날 공시했다.차량용 반도체 부품을 재공급 받은 데 따라 이뤄진 조치다.',
    '지노믹트리는 반도체 기반 디지털 PCR, 체외진단 기기 등을 제조하는 옵토레인의 지분 4.67%(4만9367주)를 50억원 가량에 현금취득하기로 결정했다고 27일 공시했다. 회사 측은 "혁신적인 체액 기반 암 조기진단 및 다중마커 동시진단 기술의 효과적인 개발을 위한 전략적 협업"이라고 설명했다.',
    '이수앱지스는 항암신약 후보물질 ISU104(성분명 바레세타맙)에 대해 중국 특허를 취득했다고 25일 공시했다. 6개국 등록 후 7번째 특허 취득이다. 이번 특허는 ErbB3 단백질이 활성화 또는 과발현된 암과 ErbB1 또는 ErbB2를 저해하는 항암제에 내성을 가지는 암 치료를 위해 ErbB3에 특이적으로 결합하는 항체에 관한 특허다.',
    '한미약품은 제넥신의 코로나19 백신 위탁생산 계약을 체결했다고 18일 공시했다.계약금액은 245억3352만원으로, 지난해 매출액 1조758억원의 2.28% 수준이다.해당 계약은 제넥신의 코로나19 백신(GX-19N)의 상용화 생산 공정 및 분석법 개발, 상용화 약물의 시생산 그리고 허가에 필요한 서류(CTD) 작성을 위탁 받아 수행하는 것으로, 해당 백신은 국내 및 인도네시아에서 판매된다.',
    '진흥기업은 363억5200만원 규모의 대구광역시 수성구 파동 수성맨션 소규모재건축사업 공사를 수주했다고 18일 공시했다.',
    '한국거래소 코스닥시장본부는 쌍용정보통신(010280)에 대해 감자 주권 및 액면분할 변경상장으로 주권매매거래정지가 해제됐다고 14일 공시했다. 해제일시는 오는 20일이다.',
    'STX는 주주배정후 실권주 일반공모 방식을 통해 보통주 680주를 유상증자하기로 결정했다고 21일 공시했다. 이번 유상증자를 통해 조달된 자금 491억원은 채무상환에 사용될 예정이다.',
    '비케이탑스는 50억원 규모로 제 10회차 무기명식 무보증 사모 전환사채 발행을 결정했다고 20일 공시했다. 표면이자율과 만기이자율은 각각 0%, 3%이다.',
    '한국거래소 코스닥시장본부는 연이비앤티(090740)에 대해 최대주주 변경을 수반하는 주식양수도 계약 체결 지연 공시 및 최대주주 변경을 수반하는 주식양수도 계약 해제를 이유로 불성실공시법인 지정을 18일 예고했다. 거래소가 불성실공시법인 지정 여부를 결정하는 시한은 2021년 6월 11일까지다. 최근 1년간 불성실공시법인 부과 벌점은 0점이다.',
    '코아시아옵틱스(196450)는 자회사 나노몰텍을 흡수합병하기로 했다고 18일 공시했다. 이번 합병은 소규모 합병으로, 합병비율은 1대 0이다. 존속법인은 코아시아옵틱스로 합병 목적은 금형 핵심기술의 내재화 및 사업 경쟁력 강화다. 합병기일은 오는 7월 21일이다.',
    '이날 관련 업계에 따르면 마이크로소프트는 2일(현지시간) 차세대 윈도우 버전을 오는 24일 공개한다고 밝혔다.이번 발표는 사티아 나델라 최고경영자(CEO)가 개발자와 크리에이터를 위한 PC 운영 체제의 개선사항을 지적한 지 일주일 만에 나온 것으로 관심을 모은다.윈도우는 마이크로소프트 전체 매출의 14%를 차지하고 있다.제이엠아이는 마이크로소프트와 소프트웨어 공식 공급계약(AR.Authorized Replicator)을 체결한 바 있어 매수세가 몰리는 것으로 풀이된다.',
    '테슬라의 주가 하락은 테슬라의 리콜 소식과 글로벌 시장 점유율 하락 등 악재가 겹친 데 따른 것으로 풀이된다. 이날 현지 언론에 따르면 테슬라는 볼트 조임 불량으로 충돌 사고 위험이 커진단 우려에 따라 전기차 5974대를 리콜하기로 했다. 테슬라 전기차의 글로벌 시장 점유율이 낮아졌단 소식도 겹쳤다. 글로벌 투자은행 크레디트스위스(CS)에 따르면 지난 4월 테슬라의 점유율이 전월 대비 18%포인트나 감소한 11%에 그쳤다.',
    '금융위원회 산하 증권선물위원회는 2일 회계처리기준을 위반해 재무제표를 작성, 공시한 유니온저축은행 등 2개사에 대해 검찰고발, 과징금 부과, 감사인지정 등의 조치를 의결했다.유니온저축은행은 지난 2013년 6월과 2014년 6월, 2015년 6월 세 차례에 걸쳐 수수료비용 및 손실보상이익 128억1500만원(총계)을 과소계상했다. 2013년 6월과 2014년 6월엔 대출채권에 대한 대손충당금을 34억3400만원 과소계상했다.증선위는 유니온저축은행에 증권발행제한 10개월과 감사인지정 1년, 회사 및 전 대표이사 2인 검찰통보 조치를 내렸다.',
    '조현렬 삼성증권 연구원은 "최근 스프레드 조정구간에서 투자자들의 화학시황 피크아웃에 대한 우려가 고조되고 있다"며 "피크아웃 여부가 하반기 업황 전망에 핵심 화두로 떠오르고 있다"고 말했다.실제 경기민감업종 특성상 스프레드(마진)가 주가에 반영되는데 최근 화학제품의 원재료인 유가가 상승하고 2월 미국 한파 영향으로 차질이 생겼던 석유화학 제품 공급이 정상화되면서 스프레드 증가폭이 둔화되고 있다.반면 한상원 대신증권 연구원은 "4월 이후 석유화학 스프레드 하락세가 이어지고 있지만 추세적 반전이 아닌 단기·계절적 조정"이라며 피크아웃 우려를 일축했다.',
    '제주항공은 이달 8일, 아시아나항공은 다음 달에 각각 인천-사이판 노선을 운항할 계획이다. 티웨이항공과 에어서울은 인천-괌 노선 운항 허가를 국토교통부에 신청했다. 현재 진에어만 인천-괌 노선을 정기편으로 운항 중인 상태로, 제주항공도 이 노선에 운항을 검토하고 있다. 대한항공은 오는 11월 해당 노선 정기편 재운항을 목표로 홈페이지에서 항공권을 판매하고 있다.성준원 신한금융투자 연구원은 일부 항공사와 여행사를 중심으로 오는 9월 출발 전세기를 준비하려는 움직임이 나타나고 있다"고 말했다. 이어 "국내 인구의 10%(550만명)가 백신 2차 접종까지 완료한다고 가정하면 지난 3월 7만3000명이었던 출국자 수가 9월 13만2000명, 10월 18만7000명, 11월 27만4000명, 12월 35만7000명 등으로 늘 것이라고 말했다.',
    '삼성바이오로직스(207940)는 김태한 이사회 의장이 1만5,000주를 장내 매도했다고 1일 공시했다. 이에 따라 김 의장이 소유한 주식은 기존 4만5,000주에서 3만주로 줄었다.김 의장은 지난달 26일, 31일, 그리고 이달 1일 3회에 걸쳐 주식을 매도했다. 처분 주식을 금액으로 환산하면 128억원이 넘는다.이에 대해 삼성바이오로직스 측은 “개인의 선택으로 회사 입장을 따로 밝히기 어렵다”고 밝혔다.',
    '한미약품(128940)은 파트너사인 스펙트럼이 바이오 베라티브(Bioverativ Therapeutix)로부터 특허 침해 소송을 당했다고 3일 공시했다. 한미약품과 체결한 계약서에 따라 스펙트럼은 한·중·일을 제외한 롤론티스의 글로벌 개발과 판권을 보유하며, 제3자로부터 제기되는 특허 침해 소송에서 스펙트럼이 면책 받는다는 내용이 포함돼있다.',
    '하이트론은 매트릭스 네트워크와 97억원 규모의 CCTV 카메라 및 NVR 저장장치 공급 계약을 체결했다고 3일 공시했다.이는 최근 매출액의 35.55%에 해당하는 액수다.',
    '에넥스(011090)는 보유 중이던 자기주식 보통주 400만주를 주당 3385원에 시간외대량매매로 처분하기로 결정했다고 3일 공시했다.처분예정금액은 135억4000만원으로, 처분예정기간은 오는 4일이다. 처분목적은 자본효율성 제고다.',
    '한국거래소 코스닥시장본부는 에프앤리퍼블릭(064090) 보통주에 대해 자본감소로 인해 오는 8일부터 신주권 변경상장일 전일까지 주권매매거래가 정지된다고 3일 공시했다.에프앤리퍼블릭 지난 4월 결손금 보전을 통한 재무구조 개선을 위해 10대 1 무상감자를 결정했다고 밝혔다.',
    '에프앤리퍼블릭 지난 4월 결손금 보전을 통한 재무구조 개선을 위해 10대 1 무상감자를 결정했다고 밝혔다',
    '킷헬스케어가 당뇨발 재생치료 플랫폼의 UAE 시장 성공적 론칭을 기반으로 중동시장 진입에 속도를 가속화 중이다.4일 글로벌 바이오헬스케어 전문기업 로킷헬스케어는 두바이 보건청(DHA;Dubai Health Authority) 산하 Rashid Hospital, 현지에서 영향력 있는 사립병원 American Hospital Dubai 등 UAE 주요 병원에 당뇨발 재생치료 플랫폼을 론칭했다고 밝혔다.국제당뇨병재단(International Diabates Federation; IDF)에 따르면 2019년 UAE 성인 인구 중 약 120만 명이 당뇨를 가지고 있다. 유병률은 16.3%로 우리나라 6.9%, 세계 평균 8.24%에 비해 현저히 높다. 60세 미만 인구의 사망원인 중 당뇨병 및 합병증이 차지하는 비율이 72.1%으로 중동지역은 당뇨발재생치료 시장 중 가장 규모가 커 시장 진입이 중요하다고 사측은 설명했다.',
    '신한금융투자는 4일 삼성전자(005930)에 대해 주가가 올해 2분기 중 바닥을 확인하고 하반기에 가파른 상승을 보일 것으로 예상했다. 비메모리 공급부족이 완화되면서 메모리 상승 사이클에 대한 확신이 강해질 것이라는 전망이다. 이에 투자의견 ‘매수(buy)’와 목표주가 10만5000원을 모두 유지했다. 신한금융투자는 삼성전자의 2분기 매출액이 전 분기 대비 5.1% 감소한 62조원, 영업이익이 같은 기간 20.6% 증가한 11조3000억원을 기록할 것으로 전망했다. 이는 영업이익 기준 시장 기대치(10조3000억원)를 웃도는 수치다. 최도연 신한금융투자 연구원은 4일 보고서에서 디램과 낸드 가격 상승, 오스틴 팹 재가동에 따른 비메모리 출하량 회복, 견조한 세트 수요 지속 등이 실적 호조 이유라고 설명했다.',
    '미국 텍사스주 오스틴에 있는 삼성전자 반도체 파운드리 공장은 미국의 기록적인 한파로 올해 2월 16일 전력과 용수 공급이 끊기면서 한 달 넘게 정상 가동을 하지 못했다. 삼성은 약 3천억∼4천억원 규모의 피해가 발생했다고 밝혔다.',
    '아이큐어는 식품의약품안전처로부터 도네페질 패취 의약품 품목허가 승인(수출용의약품)을 받았다고 3일 공시했다. 회사측은 “알츠하이머병 환자를 대상으로 하루 1회 복용하는 도네페질 경구제를 주 2회 부착하는 제형으로 개발한 개량신약으로, 경구제 대비 복약 순응도를 개선했다”고 설명했다.',
    '동아에스티는 최근 스텔라라 바이오시밀러(바이오의약품 복제약) DMB-311의 유럽 임상 1상을 성공적으로 마쳤다고 4일 밝혔다.스텔라라는 얀센이 개발한 염증성 질환 치료제다. 면역매개물질인 인터루킨(IL)-12와 IL-23의 ‘p40’ 서브유닛(subunit) 단백질을 차단해 염증세포의 활성화를 억제한다.유럽 임상 1상은 건강한 성인 296명을 대상으로 진행했다. DMB-3115와 스텔라라의 피하 투여 시 약동학적 특성 및 안전성, 면역원성을 비교했다. 그 결과 두 약물간의 생물학적 동등성이 약동학적 변수 지표를 기준으로 입증됐다. 안전성 및 면역원성에서도 유의한 차이가 없었다.바이오시밀러는 복제약인 만큼 용량을 결정하는 임상 2상을 생략할 수 있다. 동아에스티는 중증도에서 중증의 만성 판상 건선 환자를 대상으로 글로벌 임상 3상을 진행한다. DMB-3115와 스텔라라를 피하 투여하고 유효성, 안전성, 면역원성을 비교한다. 동아쏘시오홀딩스 계열사인 디엠바이오에서 생산한 임상시료를 사용한다.',
    '동아에스티, 스텔라 바이오시밀러 유럽 임상 1상 완료',
    '동아ST, 스텔라라 바이오시밀러 유럽 임상1상서 안전성 확인',
    '에스씨엠생명과학은 아토피피부염 줄기세포치료제의 치료목적 임상시험과 관련된 논문이 피부과 분야 국제학술지(The Journal of Dermatology)에 게재됐다고 25일 밝혔다.에스씨엠생명과학은 현재 아토피피부염 줄기세포치료제 SCM-AGH에 대한 임상 2상을 진행 중이다.',
    '세포치료제 전문 바이오기업 SCM생명과학은 25일 자사의 아토피 피부염 줄기세포치료제 SCM-AGH에 대한 치료목적 임상시험과 관련된 내용을 담은 논문이 피부과분야 국제학술지인 일본 피부과학 학술지(The Journal of Dermatology)에 이달 14일에 게재됐다고 밝혔다.The Journal of Dermatology는 일본 피부과 협회와 아시아 피부과 협회가 협력해 발행하는 학술지로 피부과 분야에서 국제적인 권위를 가진 학술지로 꼽힌다. 현재 SCM생명과학은 지난 2월부터 SCM-AGH에 대한 상업화 임상2상을 진행중이다.',
    '이날 삼성제약은 췌장암 치료제 ‘리아백스주’의 3상 임상시험 CSR를 수령했다고 밝혔다.삼성제약은 지난 2015년 11월부터 2020년 4월까지 약 5년간 연세대학교 세브란스병원을 포함한 전국 16개 병원에서 총 148명의 국소진행성 및 전이성 췌장암 환자를 대상으로 기존의 췌장암 치료제인 항암제 젬시타빈과 카페시타빈에 리아백스주를 병용 투여해 안전성과 유효성을 입증하기 위한 3상 임상시험을 진행했다. 리아백스주는 젬백스앤카엘이 개발한 펩타이드 조성물 ‘GV1001’을 췌장암 치료제로 개발한 제품이다.결과보고서에 의하면 GV1001은 췌장암 환자에게 안전하게 투여할 수 있는 약제이며 젬시타빈/카페시타빈과 GV1001 병용 투여 시에 젬시타빈/카페시타빈 투여 대비 median OS(생존 중간값) 및 TTP(종양 진행까지의 시간)에서 통계적으로 유의한 차이를 보인 것으로 확인됐다(p=0.021).',
    '융위원회 산하 증권선물위원회는 2일 회계처리기준을 위반해 재무제표를 작성, 공시한 유니온저축은행 등 2개사에 대해 검찰고발, 과징금 부과, 감사인지정 등의 조치를 의결했다.유니온저축은행은 지난 2013년 6월과 2014년 6월, 2015년 6월 세 차례에 걸쳐 수수료비용 및 손실보상이익 128억1500만원(총계)을 과소계상했다. 2013년 6월과 2014년 6월엔 대출채권에 대한 대손충당금을 34억3400만원 과소계상했다.증선위는 유니온저축은행에 증권발행제한 10개월과 감사인지정 1년, 회사 및 전 대표이사 2인 검찰통보 조치를 내렸다.',
    '증선위, 회계처리기준 위반 유니온저축은행 검찰고발',
    '모건스탠리는 지난 5월 30일 전기자동차(EV) 배터리 산업의 패러다임 변화로 인해 배터리 제조사들의 경쟁 과열이 예상된다며 삼성SDI에 대해 투자의견을 기존 중립에서 비중축소로, 목표주가를 57만원에서 55만원으로 각각 하향 조정한 바 있다.',
    '정부의 약 배달 서비스 제한적 허용 방침에 대해 대한약사회가 강력 반발하고 나섰다.김대업 대한약사회장은 11일 긴급기자회견을 열고 "의약품 배달 금지는 국민을 불편하게 하는 규제가 아니라 안전을 위한 제도적 장치"라며 "약 배달은 절대 불가하다"고 밝혔다.',
    '신성이엔지는 병원과 백신접종센터에서 신종 코로나바이러스 감염증(코로나19) 확산을 차단하는 확장형 음압격리 시스템이 조달청 혁신제품으로 선정됐다고 11일 밝혔다.',
    '가상자산 시장 대장주 비트코인(BTC)이 각국 규제기관의 집중포화로 시세가 급락하고 가상자산 시장내 영향력이 감소하는 등 고전하고 있다. 급기야 채굴과정의 환경문제까지 지적되면서 골드만삭스, JP모간 등 월가 주요 투자은행들은 "조만간 이더리움(ETH)이 비트코인을 추월할 수 있다"는 예측까지 내놓고 있다.',
    '하나금융투자는 롯데칠성에 대해 클라우드 생맥주와 수제맥주의 판매 호조로 2분기 호실적을 기록하며 올해 적자 규모를 대폭 줄일 것이라고 9일 전망했다. 롯데칠성 주식가격은 연초대비 47% 상승했지만, 추가 상승 가능성이 있어 매수 및 유지 전략이 유효하다는 것이다.',
    '2조원 이상 기업가치 인정 받아.적자폭 늘어 몸값 고평가 논란‘마켓컬리’ 운영사 컬리가 기업공개(IPO)를 앞두고 기존 투자자들로부터 2000억원이 넘는 투자를 추가로 받는 데 성공했다. 이 과정에서 종전의 두 배 수준인 2조원대 기업가치를 인정받았다. 그러나 신규 투자자를 찾지 못한 채 투자유치를 종료하면서, 몸값이 너무 오른 탓에 투자 매력이 떨어지는 것 아니냐는 지적이 나오고 있다.',
    '300억원 투자 협의 중넥스턴바이오는 러시아 코로나19 백신 코비박의 한국 생산과 기술이전 및 글로벌 판매를 위해 300억원을 투자키로 하는 투자합의서(MOA)를 엠피코퍼레이션(MPC)과 체결했다고 11일 밝혔다.MPC는 국내에서 코비박 사업을 총괄하고 있는 특수목적법인(SPC)이다. 양측은 이번 협약에 따라 코비박의 국내 생산을 위한 기술이전 및 국내·외 백신 유통을 위한 업무 협의를 진행할 예정이다.코비박은 러시아 추마코프연구소에서 개발한 코로나19 불활성화 백신이다. 지난 2월 러시아 보건부로부터 사용을 승인받았다.'
]

prediction(text_set)

MAX_LEN = 512

corp_name_df = pd.read_csv('/content/drive/MyDrive/data/stock_name.csv', index_col = 0)

two_word_corp = ['CJ CGV', 'CJ ENM', 'CJ제일제당 우', 'CSA 코스믹', 'JYP Ent.', 'KG ETS', 'KH E&T', 'KH 일렉트론', 'KH 필룩스',
                    'LS ELECTRIC', 'SM C&C', 'SM Life Design', 'THE E&M', 'THE MIDONG', 'YG PLUS', '리더스 기술투자',
                    '미래에셋대우스팩 5호', '블루베리 NFT', '비보존 헬스케어', '신세계 I&C', '에이프로젠 H&G','에이프로젠 KIC', '포스코 ICT']

acronym = {'SK바사':'SK바이오사이언스', '네이버':'NAVER', 'SKIET':'SK아이이테크놀로지', '진원생명' : '진원생명과학',
               '삼성바이오' : '삼성바이오로직스', '삼바' : '삼성바이오로직스', 'RF머트':'RF머트리얼즈', '기아차':'기아','SKT':'SK텔레콤',
               '두산인프라':'두산인프라코어', '한국타이어':'한국타이어앤테크놀로지','하이마트':'롯데하이마트','LGD':'LG디스플레이',
               '하이닉스':'SK하이닉스','포스코':'POSCO','현대차그룹':'현대차','현대자동차':'현대차','OCI머티리얼즈':'OCI','네오위즈게임즈':'네오위즈',
               '소마젠':'소마젠(Reg.S)','JYP엔터':'JYP Ent.','뉴지랩':'뉴지랩파마','YG엔터':'와이지엔터테인먼트', '포스코ICT':'포스코 ICT',
               '삼성SDS':'삼성에스디에스','KAI':'한국항공우주','동부제철':'KG동부제철','초록뱀':'초록뱀미디어','현대중공업':'현대중공업지주',
               '한화케미칼':'한화솔루션', 'NHN엔터테인먼트':'NHN', 'NHN엔터':'NHN','LS산전':'LS ELECTRIC'}

def extract_corpname(text):
  pat = re.compile('\[[^\[\]]*\]|\([^\(\)]*\)|[,.\"\'`를은는을]')
  title = pat.sub("", text)
  title_tkn = title.split(" ")
  disc_corp_name = []

  for corp_name in corp_name_df.values:
      corp_name = corp_name[0]
      if corp_name in two_word_corp:
          split_name = corp_name.split(" ")
          if all([name_tkn in title_tkn for name_tkn in split_name]):
              disc_corp_name.append(corp_name)
      elif corp_name in title_tkn:
          disc_corp_name.append(corp_name)
      elif any([acronym.get(token) == corp_name for token in title_tkn]):
          disc_corp_name.append(corp_name)

  if len(disc_corp_name) == 0:
      result = None
  elif len(disc_corp_name) > 1:
      result = disc_corp_name[0]
  else:
      result =  disc_corp_name[0]

  return result

class RealTimeNews(object):
    def __init__(self):
        self.last_news1 = ''
        self.last_news2 = ''
        self.temp = []

        columns = ['title', 'content', 'wrtdate']
        df = pd.DataFrame(columns=columns)

        df.to_csv('/content/drive/MyDrive/data/RealTimeNews.csv')


    # 기업/종목분석 뉴스
    def crawling(self):
        print("기업/종목 뉴스 crawling start")
        news_url = 'https://finance.naver.com/news/news_list.nhn?mode=LSS3D&section_id=101&section_id2=258&section_id3=402&date={}&page=1'
        main_url = 'https://finance.naver.com'
        total = []
        today = date.today().isoformat()

        req = requests.get(news_url.format("".join(today.split("-"))),
                           headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(req.text, 'html.parser')
        try:
            art_sub_dt = soup.select('dt.articleSubject')
            art_sub_dd = soup.select('dd.articleSubject')
            art_sub = art_sub_dd + art_sub_dt
            art_sum = soup.select('dd.articleSummary')
            if len(art_sub) == 0:
                pass

            for subject, summary in zip(art_sub, art_sum):
                art_link = subject.select_one('a')['href']
                art_link = art_link.replace('§', '&sect')

                req2 = requests.get(main_url+art_link, headers={'User-Agent': 'Mozilla/5.0'})
                soup2 = BeautifulSoup(req2.text, 'html.parser')

                art_title = soup2.select_one('div.article_info > h3').text.strip()
                art_wdate = soup2.select_one('span.article_date').text.strip()
                art_cont = soup2.select_one('div.articleCont').text.strip()

                if art_title == self.last_news1:
                    break

                result = {
                          'title': self.cleartext(art_title),
                          'content': self.cleartext(art_cont),
                          'wrtdate': art_wdate
                          }
                total.append(result)

        except:
            pass

        try:
            if self.last_news1 == total[0]['title'] :
                print("새로운 뉴스 없음")
            else:
            
                self.last_news1 = total[0]['title']
                self.temp.extend(total)
        except IndexError:
            print("새로운 뉴스 없음")

    def crawling2(self):
        print("공시/메모 crawling start")

        news_url = 'https://finance.naver.com/news/news_list.nhn?mode=LSS3D&section_id=101&section_id2=258&section_id3=406&date={}&page=1'
        main_url = 'https://finance.naver.com'

        today = date.today().isoformat()
        total = []

        req = requests.get(news_url.format("".join(today.split("-"))),
                           headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(req.text, 'html.parser')

        art_sub = soup.select('dt.articleSubject')
        art_sum = soup.select('dd.articleSummary')
        if len(art_sub) == 0:
            pass

        for subject, summary in zip(art_sub, art_sum):
            art_link = subject.select_one('a')['href']
            art_link = art_link.replace('§', '&sect')

            req2 = requests.get(main_url + art_link, headers={'User-Agent': 'Mozilla/5.0'})
            soup2 = BeautifulSoup(req2.text, 'html.parser')

            art_title = soup2.select_one('div.article_info > h3').text.strip()
            art_wdate = soup2.select_one('span.article_date').text.strip()
            art_cont = soup2.select_one('div.articleCont').text.strip()

            if art_title == self.last_news2:
                break

            result = {
                'title': self.cleartext(art_title),
                'content': self.cleartext(art_cont),
                'wrtdate': art_wdate
            }
            total.append(result)
        try:
            if self.last_news2 == total[0]['title'] :
                print("새로운 뉴스 없음")
            else:
                    
                self.last_news2 = total[0]['title']
                self.temp.append(total)
        except IndexError:
            print("새로운 뉴스 없음")

    def start(self, interval):
        self.crawling()
        self.crawling2()
        Timer(interval, self.start, [interval]).start()

    def get(self):
      return self.temp

    def cleartext(self, text):
        pat1 = re.compile('[a-zA-Z0-9]*[@].*|[ㄱ-ㅎ가-힣]{3}[\s]?기자|▶.*', re.DOTALL)
        pat2 = re.compile('\[[^\[\]]*\]|\([^\(\)]*\)|Copyrights.*|관련뉴스해당.*|<[^<>]*>|'
                          '한국경제TV|조선비즈|아시아경제|머니투데이|연합뉴스|한국경제|이데일리|매일경제|【[^【】]*】', re.DOTALL)

        text = pat1.sub("", text)
        text = pat2.sub("", text)

        return text.strip()

rtn = RealTimeNews()
rtn.start(60)

rtnews_dict = rtn.get()

content = rtnews_dict
print(content)

