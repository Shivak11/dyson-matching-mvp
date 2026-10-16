"""Use OpenRouter's explicit Mistral file parser for conditional text crops."""
import base64
from PIL import Image
from pipeline_api import Client,parse_generation


def one_page_pdf(jpeg):
    data=jpeg.read_bytes()
    with Image.open(jpeg) as image:
        if image.format!='JPEG' or image.mode!='RGB':raise ValueError('OCR PDF needs an RGB JPEG crop')
        width,height=image.size
    stream=f'q {width} 0 0 {height} 0 0 cm /Im0 Do Q'.encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>'.encode(),
        f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n'.encode()+data+b'\nendstream',
        f'<< /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream']
    pdf=bytearray(b'%PDF-1.4\n');offsets=[0]
    for index,obj in enumerate(objects,1):
        offsets.append(len(pdf));pdf.extend(f'{index} 0 obj\n'.encode()+obj+b'\nendobj\n')
    offset=len(pdf);pdf.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for value in offsets[1:]:pdf.extend(f'{value:010} 00000 n \n'.encode())
    pdf.extend(f'trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n'.encode())
    return bytes(pdf)


def extract_annotations(response,model):
    parse_generation(response,'openrouter')
    usage=response.get('usage',{})
    if usage.get('prompt_tokens',model['input_token_bound']+1)>model['input_token_bound']:
        raise ValueError('OCR downstream input exceeds reserved bound')
    annotations=response['choices'][0]['message'].get('annotations',[])
    files=[entry['file'] for entry in annotations if entry.get('type')=='file' and isinstance(entry.get('file'),dict)]
    if len(files)!=1 or not isinstance(files[0].get('hash'),str):raise ValueError('Expected one independent file-parser annotation')
    parts=files[0].get('content',[])
    if not isinstance(parts,list):raise ValueError('Invalid OCR annotation content')
    text=[part['text'] for part in parts if part.get('type')=='text' and isinstance(part.get('text'),str)]
    if not text:raise ValueError('File-parser extraction is missing; model-generated text is not OCR evidence')
    return {'literal_texts':text,'annotation_file_hash':files[0]['hash'],'engine':'mistral-ocr',
            'evidence_source':'server file-parser annotations; downstream answer excluded'}


def read_crop(client,job,jpeg):
    model=client.config['models']['ocr']
    if model['provider']!='openrouter':raise ValueError('OCR must use OpenRouter')
    pdf=one_page_pdf(jpeg)
    payload={'model':model['model'],'max_tokens':model['max_output_tokens'],'reasoning':{'enabled':False},
      'response_format':{'type':'json_object'},'usage':{'include':True},
      'provider':{'only':model['provider_only'],'allow_fallbacks':False,
         'max_price':{'prompt':model['input_usd_per_million'],'completion':model['output_usd_per_million']}},
      'plugins':[{'id':'file-parser','pdf':{'engine':'mistral-ocr'}}],
      'messages':[{'role':'user','content':[{'type':'text','text':'Return JSON {"processed":true}. Do not identify products or add text. The file-parser annotations will be retained separately.'},
        {'type':'file','file':{'filename':'region.pdf','file_data':'data:application/pdf;base64,'+base64.b64encode(pdf).decode()}}]}]}
    reservation=(model['input_token_bound']*model['input_usd_per_million']+model['max_output_tokens']*model['output_usd_per_million'])/1e6+2*model['maximum_parser_fee_usd']
    return client._call(job,'ocr',model,payload,'https://openrouter.ai/api/v1/chat/completions',reservation,
                        lambda response:extract_annotations(response,model))


class OCRClient(Client):
    def _append(self,record):
        if record.get('operation')=='ocr' and record.get('cost_basis') in ('provider_reported_cost','reported_tokens_and_configured_rates'):
            # Keep an extra parser-fee reserve until its inclusion in billing is proved.
            fee=self.config['models']['ocr']['maximum_parser_fee_usd']
            record['downstream_accounted_cost_usd']=record['estimated_cost_usd']
            record['downstream_cost_basis']=record['cost_basis']
            record['ocr_parser_fee_reserve_usd']=fee
            record['estimated_cost_usd']+=fee
            record['cost_basis']+='_plus_unreconciled_ocr_fee_reserve'
            if record['estimated_cost_usd']>record['reserved_cost_usd']+1e-12:
                record.update(status='error',error='OCR cost plus fee reserve exceeded its monetary reservation')
        return super()._append(record)
