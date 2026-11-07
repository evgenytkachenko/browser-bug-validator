"""Record only explicit human labels; never infer ratings, names, dates, or rationales."""
import argparse
from datetime import datetime
import json
from pathlib import Path

DIMENSIONS={'groundedness','relevance','uncertainty'}
NORMALIZE={'P':'pass','F':'fail','?':'unknown','pass':'pass','fail':'fail','unknown':'unknown'}

def convert(feedback,index):
    for key in ['reviewer','reviewed_at','source_message_id']:
        if not isinstance(feedback.get(key),str) or not feedback[key].strip():
            raise ValueError(f'{key} must come from the actual human response')
    stamp=datetime.fromisoformat(feedback['reviewed_at'].replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('reviewed_at needs the actual timezone offset')
    lookup={r['case_id']:r['packet_id'] for r in index['packets']}
    rows=feedback.get('labels')
    if not isinstance(rows,list) or not rows:raise ValueError('No actual human labels supplied')
    output=[];seen=set()
    for row in rows:
        case=row.get('case_id')
        if case not in lookup or case in seen:raise ValueError('Unknown or duplicate case')
        seen.add(case)
        values=row.get('dimensions',{})
        if set(values)!=DIMENSIONS or any(v not in NORMALIZE for v in values.values()):
            raise ValueError('Supply all three explicit P/F/? or pass/fail/unknown ratings')
        if not isinstance(row.get('rationale'),str) or not row['rationale'].strip():
            raise ValueError('Record a real human rationale; do not invent one')
        output.append({'case_id':case,'packet_id':lookup[case], 'reviewer':feedback['reviewer'],
                       'reviewed_at':feedback['reviewed_at'],'source':'human',
                       'source_message_id':feedback['source_message_id'],
                       'dimensions':{k:NORMALIZE[v] for k,v in values.items()},'rationale':row['rationale']})
    return {'rubric_version':index['rubric_version'],'labels':output,
            'provenance_note':'Explicit labels transcribed from the identified user message. This script does not independently authenticate the sender.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('feedback',type=Path);parser.add_argument('--index',type=Path,default=Path(__file__).parent/'packets/index.json');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Refusing to overwrite prior human labels')
    result=convert(json.loads(args.feedback.read_text()),json.loads(args.index.read_text()))
    with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'recorded_cases':len(result['labels']),'output':str(args.output)}))

if __name__=='__main__':main()
