from typing import Literal
from pydantic import BaseModel, Field, field_validator

class Generate(BaseModel):
    text: str = Field(min_length=5, max_length=30000)
    category: Literal['뉴스','이슈','연예','경제','AI'] = 'AI'
    ratio: Literal['4:5','1:1','9:16'] = '4:5'
    count: int = Field(default=0, ge=0, le=10)
    engine: Literal['local','ai'] = 'local'
    image_mode: Literal['design','upload','web','video','ai'] = 'design'
    asset_id: str = ''
    source_url: str = Field(default='', max_length=2000)
    source_name: str = Field(default='직접 입력', min_length=1, max_length=150)
    tone: Literal['후킹형','정보형','공감형','질문형'] = '후킹형'
    cta: str = Field(default='나중에 다시 볼 수 있도록 저장하세요. 여러분의 생각은 댓글로 알려주세요.', max_length=160)

class Slide(BaseModel):
    title: str = Field(min_length=1, max_length=65)
    body: str = Field(default='', max_length=230)
    asset_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

class Edit(BaseModel):
    slides: list[Slide] = Field(min_length=1, max_length=10)
    caption: str = Field(max_length=2200)
    source_name: str = Field(max_length=150)
    source_url: str = Field(max_length=2000)
    facts_checked: bool = False
    rights_checked: bool = False

class Schedule(BaseModel):
    at: str

class DailySchedule(BaseModel):
    enabled: bool = False
    hour: int = Field(default=8, ge=0, le=23)
    daily_target: int = Field(default=10, ge=1, le=10)
    categories: list[Literal['뉴스','이슈','연예','경제','AI']] = Field(min_length=1, max_length=5)

class UrlInput(BaseModel):
    url: str = Field(max_length=2000)

class AssetUrl(UrlInput):
    credit: str = Field(min_length=1, max_length=1000)
