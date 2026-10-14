import os
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import json,time,hashlib
from pathlib import Path
import numpy as np
import torch
from transformers import AutoModel,AutoTokenizer
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/movement/comparison'
MODEL=Path(r'C:\Users\zhiyu\Documents\ManifoldLLm\Ethan\artifacts\hf_cache\hub\models--Qwen--Qwen3-4B\snapshots\1cfa9a7208912126459214e8b04321603b3df60c')
def main():
 start=time.time();torch.set_num_threads(4);texts=json.loads((OUT/'prompts.json').read_text());tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True,trust_remote_code=False)
 lengths=[len(tokenizer(t)['input_ids']) for t in texts];print('tokens',min(lengths),max(lengths),sum(lengths),'loading',flush=True)
 model=AutoModel.from_pretrained(MODEL,local_files_only=True,trust_remote_code=False,dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda').eval();model.requires_grad_(False)
 path=OUT/'qwen-features.npy';dim=model.config.hidden_size;vectors=np.lib.format.open_memmap(path,mode='w+',dtype=np.float32,shape=(len(texts),dim));batch=4
 with torch.inference_mode():
  for i in range(0,len(texts),batch):
   tokens=tokenizer(texts[i:i+batch],padding=True,truncation=False,return_tensors='pt').to('cuda');hidden=model(**tokens,use_cache=False).last_hidden_state.float();mask=tokens.attention_mask.unsqueeze(-1).float();pooled=(hidden*mask).sum(1)/mask.sum(1);vectors[i:i+batch]=pooled.cpu().numpy()
   if i%128==0:print(json.dumps({'done':min(i+batch,len(texts)),'total':len(texts),'seconds':round(time.time()-start,1),'peak_mb':round(torch.cuda.max_memory_allocated()/1024**2)}),flush=True);vectors.flush()
 vectors.flush();meta={'samples':len(texts),'dimensions':dim,'seconds':time.time()-start,'max_tokens':max(lengths),'total_tokens':sum(lengths),'truncation':False,'model_path':str(MODEL),'torch':torch.__version__,'peak_gpu_mb':torch.cuda.max_memory_allocated()/1024**2,'prompts_sha256':hashlib.sha256((OUT/'prompts.json').read_bytes()).hexdigest(),'features_sha256':hashlib.sha256(path.read_bytes()).hexdigest()};(OUT/'qwen-metadata.json').write_text(json.dumps(meta,indent=2));print('DONE',meta,flush=True)
if __name__=='__main__':main()
