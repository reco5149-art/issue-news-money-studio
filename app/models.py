from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

class Generate(BaseModel):
    text: str = Field(min_length=5, max_length=30000)
    category: Literal['뉴스','이슈','연예','경제','AI'] = 'AI'
    ratio: Literal['4:5','1:1','9:16'] = '4:5'
    count: int = Field(default=0, ge=0, le=10)
    engine: Literal['local','ai'] = 'local'
    image_mode: Literal['design','upload','web','video','ai'] = 'design'
    ai_image_provider: Literal['openai','kie'] = 'openai'
    asset_id: str = ''
    video_asset_ids: list[str] = Field(default_factory=list,max_length=10)
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
    acknowledge_unverified_rights: bool = False

class PublicationPolicy(BaseModel):
    enabled: bool = False
    acknowledge_unverified_rights: bool = False

class DailySchedule(BaseModel):
    enabled: bool = False
    hour: int = Field(default=8, ge=0, le=23)
    daily_target: int = Field(default=10, ge=1, le=20)
    categories: list[Literal['뉴스','이슈','연예','경제','AI']] = Field(min_length=1, max_length=5)

class UrlInput(BaseModel):
    url: str = Field(max_length=2000)

class VideoFrames(UrlInput):
    count: int = Field(default=5,ge=0,le=10)

class FrameCleanup(BaseModel):
    asset_ids: list[str] = Field(min_length=1,max_length=20)
    count: int = Field(ge=0,le=10)

class AssetUrl(UrlInput):
    credit: str = Field(min_length=1, max_length=1000)

class PostingCadence(BaseModel):
    enabled: bool = False
    autopilot: bool = False
    daily_limit: int = Field(default=20, ge=1, le=20)
    start_hour: int = Field(default=6, ge=0, le=23)
    batch_size: int = Field(default=2, ge=2, le=3)
    batch_interval: int = Field(default=90, ge=60, le=90)
    item_interval: int = Field(default=10, ge=5, le=20)

    @model_validator(mode='after')
    def enough_slots(self):
        if 1 <= self.start_hour < 6:
            raise ValueError('새벽 1시부터 6시까지는 게시하지 않습니다.')
        slots = []
        for start in range(self.start_hour * 60, 1440, self.batch_interval):
            for i in range(self.batch_size):
                minute = start + i * self.item_interval
                if minute < 1440 and not 60 <= minute < 360:
                    slots.append(minute)
        if len(slots) < self.daily_limit:
            raise ValueError('설정한 시간 안에 하루 게시 개수를 배치할 수 없습니다. 시작 시각을 앞당기세요.')
        return self

class BatchReservation(BaseModel):
    post_ids: list[str] = Field(min_length=1, max_length=100)
    start_at: str | None = None
    consecutive: bool = False

    @field_validator('post_ids')
    @classmethod
    def unique_ids(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('같은 게시물을 중복 선택할 수 없습니다.')
        return value
