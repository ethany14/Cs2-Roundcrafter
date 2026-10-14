from langchain_core.messages import AIMessage
from cs2_agent.review import ReviewHost
from cs2_agent.tools import Tool,function


def test_real_kernel_requires_reference_evidence_before_finish(tmp_path):
    steps=[('finish_task',{'text':'premature'}),('inspect_player_information',{'case_id':'q'}),('inspect_case_evidence',{'case_id':'q'}),
           ('retrieve_pro_cases',{'case_id':'q'}),('finish_task',{'text':'still premature'}),
           ('inspect_case_evidence',{'case_id':'ref'}),('finish_task',{'text':'Offline fixture; not an AI judgment.'})]
    class Model:
        def invoke(self,messages,tools):
            name,args=steps.pop(0)
            return AIMessage(content='',tool_calls=[{'id':str(len(steps)),'name':name,'args':args}])
    tools=[Tool(function('inspect_player_information','Read knowledge',{'case_id':{'type':'string'}}),lambda a:{'decision_gate':False}),
           Tool(function('inspect_case_evidence','Read',{'case_id':{'type':'string'}}),lambda a:{'id':a['case_id']}),
           Tool(function('retrieve_pro_cases','Retrieve',{'case_id':{'type':'string'}}),lambda a:{'matches':[{'id':'ref'}]})]
    host=ReviewHost(tmp_path/'task',Model(),tools,case_id='q',request='Offline test',max_calls=7)
    try:
        assert host.run(slice_steps=100)['reason']=='completed'
        assert host.state['calls']==7
        assert host.state['evidence_audit']['inspected']==['q','ref']
        assert host.state['result']=='Offline fixture; not an AI judgment.'
    finally:host.close()
