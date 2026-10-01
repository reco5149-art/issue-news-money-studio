const assert=require('node:assert/strict');
const {parseSourceLink}=require('../public-demo/source.js');
for(const s of ['https://youtu.be/abcdefghijk?si=123','https://www.youtube.com/watch?v=abcdefghijk&t=10','https://m.youtube.com/shorts/abcdefghijk','https://www.youtube.com/live/abcdefghijk'])assert.equal(parseSourceLink(s).videoId,'abcdefghijk');
for(const s of ['javascript:alert(1)','file:///test','https://user:pass@example.com','https://youtube.com/@channel','https://youtu.be/bad'])assert.throws(()=>parseSourceLink(s));
assert.equal(parseSourceLink('https://youtube.com.evil.example/watch?v=abcdefghijk').videoId,null);
assert.equal(parseSourceLink('https://news.example.com/article/1').kind,'웹 출처');
console.log('11 source-link cases passed');
