"""Sourced learning cards. Page descriptions verified; videos/lineups not verified."""
import json
from .casebook import ROOT,get_case


def load_cards():return json.loads((ROOT/'experiments/knowledge/resources.json').read_text(encoding='utf-8'))
def card_text(card):return card['title']+' '+card['summary']+' '+' '.join(card['tags'])


def search_resources(db,case_id,query=''):
    from .embeddings import semantic,hybrid,method
    case=get_case(db,case_id)
    terms=query.casefold().split()
    pool=[]
    for card in load_cards():
        if card['map']!=case['map'] or card['side'] not in (case['side'],'both'):continue
        pool.append((sum(t in card_text(card).casefold() for t in terms),card))
    sims,info=semantic('learning_resources',[card_text(c) for _,c in pool],query)
    ranked=[]
    for i,(combined,(score,card)) in enumerate(zip(hybrid([s for s,_ in pool],sims,info),pool)):
        if terms and not score and (sims is None or sims[i]<info['floor']):continue
        ranked.append((combined,card))
    ranked.sort(key=lambda pair:(-pair[0],pair[1]['id']))
    return {'case_id':case_id,'resources':[c for _,c in ranked[:5]],'retrieval_method':method(info,'map/side filters + keyword match'),
            'use':'Learning references only. Map and side filters do not establish tactical fit. Do not invent lineup steps or assume current patch validity.',
            'verified_scope':'Public page title, tags and textual description only; no video viewing or coach validation.'}
