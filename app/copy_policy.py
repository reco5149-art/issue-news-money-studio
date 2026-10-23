"""Public caption formatting; source records stay on the post and its assets."""
import re

TITLE_LIMIT = 32
BODY_LIMIT = 70
CAPTION_LIMIT = 1400
BROADCASTER = re.compile(r'(?<![A-Za-z])(?:iMBC|한국경제TV|KBS|MBC|SBS|JTBC|YTN|MBN|EBS|OBS|TV\s*CHOSUN|TV조선|채널\s*A|연합뉴스(?:TV)?|한국방송|문화방송)(?:\s*NEWS)?(?![A-Za-z])',re.I)

def has_broadcaster(text):return bool(BROADCASTER.search(text))

def public_source_label(source):
    return '' if has_broadcaster(source) else source
URL = re.compile(r'https?://[^\s<>\[\]()]+|www\.[^\s<>\[\]()]+|(?<![\w@])(?:[A-Za-z0-9-]+\.)+(?:com|net|org|kr|io|ai|gov|edu)(?:/[^\s<>\[\]()]*)?', re.I)


def caption_urls(text):
    return list(dict.fromkeys(m.group().rstrip('.,;') for m in URL.finditer(text)))

def story_paragraphs(text):
    """Readable caption paragraphs without adding or rewriting any claims."""
    text=public_caption(text)
    if len(text)<180 or text.count('\n\n')>=2:return text
    # Preserve existing lines; split long prose on sentence boundaries only.
    blocks=[]
    for line in text.splitlines():
        line=line.strip()
        if not line:continue
        sentences=re.split(r'(?<=[.!?])\s+',line)
        for i in range(0,len(sentences),2):blocks.append(' '.join(sentences[i:i+2]))
    return '\n\n'.join(blocks)

def compound_cta(text):
    paragraphs=[p for p in text.split('\n\n') if p.strip() and not p.lstrip().startswith(('#','출처:','이미지:'))]
    if not paragraphs:return False
    end=paragraphs[-1]
    save=bool(re.search(r'저장(?:하|해|해두)',end))
    share=bool(re.search(r'공유(?:하|해)',end))
    reply=bool(re.search(r'댓글|(?:생각|의견).{0,15}(?:나눠|알려|남겨)|[?？]',end))
    like=bool(re.search(r'좋아요.{0,10}(?:눌러|누르)',end))
    return sum((save,share,reply,like))>1


def public_caption(text):
    # Preserve the label of Markdown links while removing the address.
    text = re.sub(r'\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)', r'\1', text)
    text = URL.sub('', text)
    text = re.sub(r'[\(\[<]\s*[\)\]>]', '', text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r'[ \t]+', ' ', line).strip()
        # Public labels only; post.source_name and evidence records remain intact.
        match=re.search(r'(?:출처|보도 출처|자료 출처)\s*[:：]',line)
        if match and has_broadcaster(line[match.end():]):
            tags=' '.join(t for t in re.findall(r'#[\w]+',line[match.end():]) if not has_broadcaster(t))
            line=(line[:match.start()].rstrip()+' '+tags).strip()
        line=re.sub(r'#[\w]+',lambda m:'' if has_broadcaster(m.group()) else m.group(),line).strip()
        if re.fullmatch(r'(?:출처|출처 링크|원문|원문 링크|참고|참고 링크|영상|확인한 보도·기록)\s*[:：]?\s*', line):
            continue
        if not line and (not lines or not lines[-1]):
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def image_caption_credit(mode, credit):
    if not credit:
        return ''
    if mode == 'video':
        return ''
    if mode == 'ai' or 'AI 생성' in credit:
        return 'AI 생성 · 설명용 이미지' + (' (KIE AI)' if 'KIE' in credit else '')
    return public_caption(credit)


def finish_caption(text, mode, credit=''):
    caption = public_caption(text)
    label = image_caption_credit(mode, credit)
    if label and label not in caption:
        caption += '\n이미지: ' + label
    return caption.strip()
