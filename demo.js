'use strict';
const $=id=>document.getElementById(id);
const sample='AI 답변, 그대로 믿어도 될까요?\nAI가 제시한 정보에는 잘못된 내용이 포함될 수 있습니다.\n중요한 숫자와 날짜는 원문 자료를 찾아 확인하세요.\n링크를 직접 열어 주장과 출처의 내용이 일치하는지 비교하세요.\n개인정보와 비밀번호는 공개 AI 서비스에 입력하지 마세요.';
let cards=[],current=0;
function splitText(text,count){
 const sentences=text.trim().split(/\n+|(?<=[.!?。])\s+/u).map(x=>x.trim()).filter(Boolean);
 const chunks=[];
 for(const sentence of sentences){for(let i=0;i<sentence.length;i+=180)chunks.push(sentence.slice(i,i+180));}
 const wanted=count||Math.min(5,Math.max(1,chunks.length));
 return chunks.slice(0,wanted).map((body,i)=>({title:i===0?'이 이야기, 함께 살펴볼까요?':`${i+1}번째 이야기`,body}));
}
function lines(ctx,text,maxWidth){let out=[],line='';for(const ch of text){if(ch==='\n'){out.push(line);line='';continue;}if(line&&ctx.measureText(line+ch).width>maxWidth){out.push(line);line=ch;}else line+=ch;}if(line)out.push(line);return out;}
function draw(){
 const card=cards[current];if(!card)return;
 const cv=$('canvas'),ctx=cv.getContext('2d');cv.width=1080;cv.height={'4:5':1350,'1:1':1080,'9:16':1920}[$('ratio').value];
 const dark=current%2===0;ctx.fillStyle=dark?'#142d24':'#f2efdf';ctx.fillRect(0,0,cv.width,cv.height);
 ctx.fillStyle=dark?'#d9edac':'#44633d';ctx.font='bold 23px sans-serif';ctx.fillText('ISSUE STUDIO  /  DEMO',75,100);
 ctx.fillStyle=dark?'#f5f4e8':'#17352a';ctx.font='bold 66px sans-serif';let y=235;
 for(const line of lines(ctx,card.title,930)){ctx.fillText(line,75,y);y+=86;}
 ctx.font='34px sans-serif';y+=65;for(const line of lines(ctx,card.body,930)){ctx.fillText(line,75,y);y+=55;}
 ctx.strokeStyle=dark?'#58705c':'#b7c1a7';ctx.beginPath();ctx.moveTo(75,cv.height-180);ctx.lineTo(1005,cv.height-180);ctx.stroke();
 ctx.font='25px sans-serif';ctx.fillText('원문을 확인하고, 나의 생각을 더해보세요.',75,cv.height-115);
 ctx.font='20px sans-serif';ctx.fillText('시연용 원문 배치 · AI 생성 아님',75,cv.height-62);ctx.fillText(`${current+1} / ${cards.length}`,935,cv.height-62);
 $('position').textContent=`${current+1} / ${cards.length}`;$('badge').textContent=$('ratio').value;
 $('title').value=card.title;$('body').value=card.body;$('prev').disabled=current===0;$('next').disabled=current===cards.length-1;
}
function generate(){const value=$('text').value.trim();if(value.length<5){$('message').textContent='원고를 5자 이상 입력하세요.';return;}cards=splitText(value,Number($('count').value));current=0;draw();$('caption').value=cards.map(c=>c.body).join('\n\n')+'\n\n여러분은 어떻게 생각하시나요?\n#카드뉴스 #정보정리 #IssueStudio';$('message').textContent=`${cards.length}장 생성했습니다. 긴 원고는 선택 장수에 맞춰 앞부분만 배치합니다. AI 요약이 아니므로 생략된 내용을 확인하세요.`;}
function download(blob,name){const a=document.createElement('a'),url=URL.createObjectURL(blob);a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('sample').onclick=()=>{$('text').value=sample;generate();};$('generate').onclick=generate;
$('apply').onclick=()=>{if(!$('title').value.trim()){ $('message').textContent='제목을 입력하세요.';return;}cards[current]={title:$('title').value.trim(),body:$('body').value};draw();$('message').textContent='카드 수정 적용 완료. 캡션은 아래에서 별도로 편집하세요.';};
$('prev').onclick=()=>{if(current>0){current--;draw();}};$('next').onclick=()=>{if(current<cards.length-1){current++;draw();}};$('ratio').onchange=draw;
$('download').onclick=()=>{$('canvas').toBlob(b=>{if(b)download(b,`issue-studio-demo-${current+1}.png`);},'image/png');};
$('captionDownload').onclick=()=>download(new Blob([$ ('caption').value],{type:'text/plain;charset=utf-8'}),'issue-studio-caption.txt');
$('text').value=sample;generate();
