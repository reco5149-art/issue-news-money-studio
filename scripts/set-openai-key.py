"""Local masked credential entry. Never log the key or publish content."""
import json
import os
import re
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'data' / 'openai-key-setup.json'


def verify_and_save(key):
    if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,300}', key):
        raise ValueError('API 키 전체를 공백 없이 붙여넣어 주세요.')
    values = dotenv_values(ROOT / '.env')
    if key == values.get('OPENAI_API_KEY'):
        raise ValueError('현재 저장된 키와 같습니다. 개인 조직에서 새로 만든 키를 넣어 주세요.')
    with httpx.Client(timeout=45, trust_env=False) as client:
        response = client.post(
            'https://api.openai.com/v1/responses',
            headers={'Authorization': 'Bearer ' + key},
            json={'model': values.get('OPENAI_TEXT_MODEL') or 'gpt-4.1-mini',
                  'input': 'Reply OK', 'max_output_tokens': 16, 'store': False})
    if response.status_code != 200:
        messages = {401: '키 인증 실패. 복사한 개인 API 키를 확인하세요.',
                    403: 'AI 요청 권한이 없습니다. 키의 Model capabilities 권한을 확인하세요.',
                    429: '사용 한도 또는 잔액 때문에 요청이 차단됐습니다. 키는 교체하지 않았습니다.'}
        raise ValueError(messages.get(response.status_code, '연결 검증에 실패했습니다. 잠시 후 다시 시도하세요.'))
    if response.headers.get('openai-organization') == 'modulabs-dxnytv':
        raise ValueError('교육기관 조직의 키입니다. Personal 조직에서 발급해 주세요.')
    result = response.json()
    if result.get('error') or result.get('status') != 'completed':
        raise ValueError('AI 응답이 완료되지 않았습니다. 기존 키는 유지합니다.')
    set_key(str(ROOT / '.env'), 'OPENAI_API_KEY', key)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps({
        'status': 'verified_saved', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'project': response.headers.get('openai-project'),
        'organization': response.headers.get('openai-organization'),
        'usage': result.get('usage'), 'server_restart_required': True
    }, ensure_ascii=False), encoding='utf-8')


def main():
    window = tk.Tk()
    window.title('Issue Studio 개인 API 연결')
    window.geometry('590x280')
    window.resizable(False, False)
    area = ttk.Frame(window, padding=22)
    area.pack(fill='both', expand=True)
    ttk.Label(area, text='OpenAI 개인 API 키 입력', font=('맑은 고딕', 14, 'bold')).pack(anchor='w')
    ttk.Label(area, text='Personal 조직에서 발급한 키를 아래에 붙여넣으세요.\n키는 채팅·로그에 표시하지 않고 이 PC의 .env에 저장합니다.',
              padding=(0, 12)).pack(anchor='w')
    entry = ttk.Entry(area, show='•', width=72)
    entry.pack(fill='x')
    status = tk.StringVar(value='소량의 실제 AI 요청(출력 최대 16토큰)으로 검증합니다.')
    ttk.Label(area, textvariable=status, wraplength=535, padding=(0, 12)).pack(anchor='w')

    def finished(message, success):
        status.set(message)
        if success:
            entry.delete(0, 'end')
            entry.configure(state='disabled')
            button.configure(text='저장 완료', state='disabled')
        else:
            button.configure(state='normal')

    def submit():
        key = entry.get().strip()
        button.configure(state='disabled')
        status.set('연결 검증 중입니다…')

        def run():
            try:
                verify_and_save(key)
                message, ok = '검증·저장 완료. 코덱스에 완료라고 알려주세요. 서버 적용을 이어갑니다.', True
            except ValueError as error:
                message, ok = str(error), False
            except Exception:
                message, ok = '네트워크 또는 저장 오류입니다. 키를 표시하지 않고 중단했습니다.', False
            window.after(0, finished, message, ok)

        threading.Thread(target=run, daemon=True).start()

    button = ttk.Button(area, text='검증 후 저장', command=submit)
    button.pack(anchor='e')
    entry.focus_set()
    window.lift()
    window.mainloop()


if __name__ == '__main__':
    main()
