"""Sourced learning cards. Page descriptions verified; videos/lineups not verified."""
import json
from .casebook import ROOT,get_case


def search_resources(db,case_id,query=''):
    case=get_case(db,case_id)
    cards=json.loads((ROOT/'experiments/knowledge/resources.json').read_text(encoding='utf-8'))
    terms=query.casefold().split()
    ranked=[]
    for card in cards:
        if card['map']!=case['map'] or card['side'] not in (case['side'],'both'):continue
        haystack=(card['title']+' '+card['summary']+' '+' '.join(card['tags'])).casefold()
        score=sum(t in haystack for t in terms)
        if terms and not score:continue
        ranked.append((score,card))
    ranked.sort(key=lambda pair:(-pair[0],pair[1]['id']))
    return {'case_id':case_id,'resources':[c for _,c in ranked[:5]],
            'use':'Learning references only. Map and side filters do not establish tactical fit. Do not invent lineup steps or assume current patch validity.',
            'verified_scope':'Public page title, tags and textual description only; no video viewing or coach validation.'}
