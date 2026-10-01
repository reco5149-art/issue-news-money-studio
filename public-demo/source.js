'use strict';
function parseSourceLink(raw){
 if(raw.length>1000)throw new Error('출처 링크는 1,000자 이내로 입력하세요.');
 let u;try{u=new URL(raw.trim());}catch{throw new Error('https://로 시작하는 전체 링크를 입력하세요.');}
 if(!['http:','https:'].includes(u.protocol)||u.username||u.password)throw new Error('일반 웹 링크만 사용할 수 있습니다.');
 const host=u.hostname.toLowerCase(), parts=u.pathname.split('/').filter(Boolean);
 const youtube=['youtube.com','www.youtube.com','m.youtube.com','youtu.be','www.youtu.be','youtube-nocookie.com','www.youtube-nocookie.com'].includes(host);
 if(youtube){
  const id=host.endsWith('youtu.be')?parts[0]:u.pathname==='/watch'?u.searchParams.get('v'):['shorts','live','embed'].includes(parts[0])?parts[1]:null;
  if(!id||!/^[A-Za-z0-9_-]{11}$/.test(id))throw new Error('유튜브 영상 링크를 입력하세요. 채널·재생목록 링크는 지원하지 않습니다.');
  return {url:`https://www.youtube.com/watch?v=${id}`,kind:'YouTube',videoId:id};
 }
 return {url:u.href,kind:'웹 출처',videoId:null};
}
if(typeof module!=='undefined')module.exports={parseSourceLink};
