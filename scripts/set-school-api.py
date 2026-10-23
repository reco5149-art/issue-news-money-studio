"""Private local setup; credentials are never printed or returned by the web app."""
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path
import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://factchat-cloud.mindlogic.ai/v1/gateway'

def model_ids(value):
    found = set()
    if isinstance(value, dict):
        for key in ('id', 'model', 'model_id'):
            item = value.get(key)
            if isinstance(item, str) and item.startswith('gpt-'):
                found.add(item)
        for child in value.values():
            found.update(model_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(model_ids(child))
    return found

def main():
    values = dotenv_values(ROOT / '.env')
    window = tk.Tk()
    window.title('Issue Studio · 세명대학교 API 설정')
    window.geometry('740x490')
    area = ttk.Frame(window, padding=22)
    area.pack(fill='both', expand=True)
    ttk.Label(area, text='학교 API 연결 · 개인 키는 그대로 보존', font=('맑은 고딕', 14, 'bold')).pack(anchor='w')
    ttk.Label(area, text='공식 API 주소 (다른 주소로 키를 보내지 않습니다)').pack(anchor='w', pady=(12, 0))
    address = ttk.Entry(area, width=90)
    address.insert(0, BASE)
    address.configure(state='readonly')
    address.pack(fill='x')
    ttk.Label(area, text='학교에서 발급한 API 키 · 채팅에 붙여넣지 마세요').pack(anchor='w', pady=(12, 0))
    key = ttk.Entry(area, show='●', width=90)
    key.pack(fill='x')
    models = {}
    for role, label in [('TEXT','문안 모델'), ('REVIEW','사진·내용 검수 모델'), ('FRAME','영상 장면 검수 모델')]:
        row = ttk.Frame(area)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=label, width=24).pack(side='left')
        combo = ttk.Combobox(row, state='readonly', width=42)
        combo.pack(side='left')
        models[role] = combo
    activate = tk.BooleanVar(value=values.get('AI_PROVIDER') == 'semyung')
    ttk.Checkbutton(area, text='저장할 때 학교 연결을 활성화 (서버 재시작 후 적용)', variable=activate).pack(anchor='w', pady=8)
    ttk.Label(area, text='문안·사진 검수용 OpenAI 계열 모델을 조회합니다. 음성 전사·AI 이미지 생성은 미지원입니다.\n학교 연결 실패 시 개인 유료 API로 자동 전환하지 않습니다.').pack(anchor='w')
    message = tk.StringVar(value='키 입력 → 지원 모델 조회 → 모델 선택 → 저장')
    ttk.Label(area, textvariable=message, wraplength=680).pack(anchor='w', pady=12)
    verified = {'key': None}

    def lookup():
        candidate = key.get().strip()
        if not candidate or any(c.isspace() for c in candidate):
            message.set('공백 없는 학교 API 키를 입력하세요.'); return
        lookup_button.configure(state='disabled')
        save_button.configure(state='disabled')
        message.set('학교에서 지원 모델을 조회하고 있습니다. 생성 요청은 하지 않습니다.')
        def work():
            try:
                with httpx.Client(timeout=30, trust_env=False) as client:
                    response = client.get(BASE+'/models/', headers={'Authorization':'Bearer '+candidate})
                if response.status_code != 200:
                    raise ValueError('학교 API 인증·모델 조회 실패 (HTTP '+str(response.status_code)+'). 키와 권한을 확인하세요.')
                choices = sorted(model_ids(response.json()))
                if not choices: raise ValueError('지원되는 OpenAI 모델 목록을 확인하지 못했습니다. 저장하지 않았습니다.')
                def done():
                    verified['key'] = candidate
                    for role, combo in models.items():
                        combo['values'] = choices
                        preferred = values.get('SEMYUNG_'+role+'_MODEL') or 'gpt-5.4-mini'
                        combo.set(preferred if preferred in choices else choices[0])
                    message.set('인증 및 모델 목록 조회 성공. 모델을 선택하고 저장하세요. 실제 생성 호환성은 별도 검증이 필요합니다.')
                    save_button.configure(state='normal')
                    lookup_button.configure(state='normal')
                window.after(0, done)
            except Exception as error:
                text = str(error) if isinstance(error, ValueError) else '학교 연결 실패. 네트워크를 확인하세요.'
                window.after(0, lambda: (message.set(text), lookup_button.configure(state='normal')))
        threading.Thread(target=work, daemon=True).start()

    def save():
        if verified['key'] != key.get().strip():
            message.set('키가 바뀌었습니다. 지원 모델을 다시 조회하세요.'); return
        path = str(ROOT / '.env')
        set_key(path, 'SEMYUNG_API_BASE_URL', BASE)
        set_key(path, 'SEMYUNG_API_KEY', verified['key'])
        for role, combo in models.items(): set_key(path, 'SEMYUNG_'+role+'_MODEL', combo.get())
        if activate.get(): set_key(path, 'AI_PROVIDER', 'semyung')
        key.delete(0, 'end')
        save_button.configure(state='disabled')
        message.set('저장 완료. 개인 OpenAI 키는 보존했습니다. 이슈 스튜디오 서버 재시작 후 적용됩니다.')

    buttons = ttk.Frame(area)
    buttons.pack(fill='x')
    lookup_button = ttk.Button(buttons, text='1. 지원 모델 조회', command=lookup)
    lookup_button.pack(side='left', padx=4)
    save_button = ttk.Button(buttons, text='2. 설정 저장', command=save, state='disabled')
    save_button.pack(side='left', padx=4)
    window.mainloop()

if __name__ == '__main__': main()
