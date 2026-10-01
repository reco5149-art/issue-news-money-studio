'use strict';
const $=id=>document.getElementById(id);
const sample='AI 답변, 그대로 믿어도 될까요?\nAI가 제시한 정보에는 잘못된 내용이 포함될 수 있습니다.\n중요한 숫자와 날짜는 원문 자료를 찾아 확인하세요.\n링크를 직접 열어 주장과 출처의 내용이 일치하는지 비교하세요.\n개인정보와 비밀번호는 공개 AI 서비스에 입력하지 마세요.';
let cards=[],current=0,source=null;
function applySource(){
 $('videoHost').replaceChildren();$('sourcePreview').hidden=true;source=null;
 if(!$('sourceUrl').value.trim()){$('sourceStatus').textContent='출처 링크 없이 직접 입력한 원고를 사용합니다.';return true;}
 try{source=parseSourceLink($('sourceUrl').value);$('sourceOpen').href=source.url;$('sourceOpen').textContent=source.kind+' 원문 열기 ↗';$('sourcePreview').hidden=false;$('videoLoad').hidden=!source.videoId;$('sourceStatus').textContent='출처를 적용했습니다. 자막·본문은 자동 수집하지 않습니다. 아래 원고를 이 출처의 내용으로 바꿔 주세요.';return true;}
 catch(e){$('sourceStatus').textContent=e.message;return false;}
}
$('sourceLoad').onclick=()=>{if(applySource()&&source){$('text').value='';$('message').textContent='출처의 자막이나 기사 본문을 붙여넣은 뒤 생성하세요. 이전 카드는 새로 생성하기 전까지 유지됩니다.';}};
$('sourceUrl').oninput=()=>{source=null;if($('text').value===sample)$('text').value='';$('sourcePreview').hidden=true;$('videoHost').replaceChildren();$('sourceStatus').textContent='변경한 링크를 적용하세요. 자막·본문은 직접 입력해야 합니다.';};
$('videoLoad').onclick=()=>{if(!source?.videoId)return;const frame=document.createElement('iframe');frame.src='https://www.youtube-nocookie.com/embed/'+source.videoId;frame.title='유튜브 출처 영상';frame.allow='encrypted-media; fullscreen; picture-in-picture';frame.referrerPolicy='strict-origin-when-cross-origin';frame.allowFullscreen=true;$('videoHost').replaceChildren(frame);};
function splitText(text,count){
 const sentences=text.trim().split(/\n+|(?<=[.!?。])\s+/u).map(x=>x.trim()).filter(Boolean);
 const chunks=[];
 for(const sentence of sentences){for(let i=0;i<sentence.length;i+=180)chunks.push(sentence.slice(i,i+180));}
 const wanted=count||Math.min(10,Math.max(1,chunks.length));
 return chunks.slice(0,wanted).map((body,i)=>({title:i===0?'이 이야기, 함께 살펴볼까요?':`${i+1}번째 이야기`,body}));
}
function lines(ctx,text,maxWidth){let out=[],line='';for(const ch of text){if(ch==='\n'){out.push(line);line='';continue;}if(line&&ctx.measureText(line+ch).width>maxWidth){out.push(line);line=ch;}else line+=ch;}if(line)out.push(line);return out;}
function draw(){
 const card=cards[current];if(!card)return;
 const cv=$('canvas'),ctx=cv.getContext('2d');cv.width=1080;cv.height={'4:5':1350,'1:1':1080,'9:16':1920}[$('ratio').value];
 const dark=current%2===0;ctx.fillStyle=dark?'#142d24':'#f2efdf';ctx.fillRect(0,0,cv.width,cv.height);
 ctx.fillStyle=dark?'#d9edac':'#44633d';ctx.font='bold 23px sans-serif';ctx.fillText('ISSUE STUDIO  /  '+$('category').value,75,100);
 ctx.fillStyle=dark?'#f5f4e8':'#17352a';ctx.font='bold 66px sans-serif';let y=235;
 for(const line of lines(ctx,card.title,930)){ctx.fillText(line,75,y);y+=86;}
 y+=65;let bodyFont=34,bodyLines=[];const cleanBody=card.body.replace(/\s+/g,' ');
 do{ctx.font=`${bodyFont}px sans-serif`;bodyLines=lines(ctx,cleanBody,930);if(bodyLines.length*bodyFont*1.6<=cv.height-235-y)break;bodyFont-=2;}while(bodyFont>=18);
 for(const line of bodyLines){ctx.fillText(line,75,y);y+=bodyFont*1.6;}
 ctx.strokeStyle=dark?'#58705c':'#b7c1a7';ctx.beginPath();ctx.moveTo(75,cv.height-180);ctx.lineTo(1005,cv.height-180);ctx.stroke();
 ctx.font='25px sans-serif';const cta=$('cta').value.trim()||'원문을 확인하고, 나의 생각을 더해보세요.';const ctaLines=lines(ctx,cta,930);ctx.fillText(ctaLines[0]+(ctaLines.length>1?'…':''),75,cv.height-115);
 ctx.font='20px sans-serif';ctx.fillText('시연용 원문 배치 · AI 생성 아님',75,cv.height-62);ctx.fillText(`${current+1} / ${cards.length}`,935,cv.height-62);
 $('position').textContent=`${current+1} / ${cards.length}`;$('badge').textContent=$('ratio').value;
 $('title').value=card.title;$('body').value=card.body;$('prev').disabled=current===0;$('next').disabled=current===cards.length-1;
}
function generate(){if(!applySource())return;const value=$('text').value.trim();if(value.length<5){$('message').textContent='원고·자막·기사 본문을 5자 이상 입력하세요. 링크만으로 내용은 생성되지 않습니다.';return;}cards=splitText(value,Number($('count').value));if($('topic').value.trim())cards[0].title=$('topic').value.trim();current=0;draw();const ending='\n\n'+$('cta').value+'\n'+$('tags').value+(source?'\n\n출처: '+source.url:'\n\n출처: 직접 입력');$('caption').value=cards.map(c=>c.body).join('\n\n').slice(0,Math.max(0,2200-ending.length))+ending;$('message').textContent=`${cards.length}장 생성했습니다. 긴 원고는 선택 장수에 맞춰 앞부분만 배치합니다. AI 요약이 아니므로 생략된 내용을 확인하세요.`;}
function download(blob,name){const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('sample').onclick=()=>{$('sourceUrl').value='';$('topic').value='AI 답변, 그대로 믿어도 될까요?';$('text').value=sample;generate();};$('generate').onclick=generate;
$('apply').onclick=()=>{if(!$('title').value.trim()){ $('message').textContent='제목을 입력하세요.';return;}cards[current]={title:$('title').value.trim(),body:$('body').value};draw();$('message').textContent='카드 수정 적용 완료. 캡션은 아래에서 별도로 편집하세요.';};
$('prev').onclick=()=>{if(current>0){current--;draw();}};$('next').onclick=()=>{if(current<cards.length-1){current++;draw();}};$('ratio').onchange=draw;
$('download').onclick=()=>{$('canvas').toBlob(b=>{if(b)download(b,`issue-studio-demo-${current+1}.png`);},'image/png');};
$('captionDownload').onclick=()=>download(new Blob([$ ('caption').value],{type:'text/plain;charset=utf-8'}),'issue-studio-caption.txt');
$('text').value=sample;generate();
