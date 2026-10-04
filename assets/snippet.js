(function(){
var P=location.href,R=performance.getEntriesByType("resource")||[],S=[],V=[],A=[],m4s=0,blob=0,seen={};
function hit(u,hint){
if(!u||seen[u]||!/^https?:/i.test(u))return;seen[u]=1;
if(/\.m3u8(\?|#|$)/i.test(u))S.push(["HLS",u]);
else if(/\.mpd(\?|#|$)/i.test(u))S.push(["DASH",u]);
else if(/\.m4s(\?|#|$)/i.test(u))m4s++;
else if(/\.(mp4|webm|mkv|avi|mov|flv|wmv|m4v)(\?|#|$)/i.test(u))V.push(u);
else if(/\.(mp3|flac|aac|ogg|wav|m4a|opus|wma)(\?|#|$)/i.test(u))A.push(u);
else if(hint==="A")A.push(u);
else if(hint==="V")V.push(u);
}
R.forEach(function(r){var n=r.name;if(/^blob:/i.test(n)){blob++;return}hit(n,"")});
document.querySelectorAll("video,audio,source").forEach(function(e){var s=e.src||e.currentSrc;if(!s)return;if(/^blob:/i.test(s)){blob++;return}hit(s,e.tagName==="AUDIO"?"A":"V")});
function pay(u){return u.indexOf("#")<0?u+"#sgref="+encodeURIComponent(P):u}
var rows=[["流媒体清单",S],["视频",V.map(function(u){return["文件",u]})],["音频",A.map(function(u){return["文件",u]})]];
var notes=[];
if(m4s)notes.push("检测到 "+m4s+" 个 m4s 分片"+(S.length?"，其主清单已在上方列出，可直接复制给下载器":"，但未找到 .mpd 主清单——该站使用 MSE 加密媒体流，嗅探不适用"));
if(blob)notes.push("检测到 "+blob+" 个 blob: 播放源（MSE），无法取得直链");
if(!S.length&&!V.length&&!A.length)notes.push("未发现任何媒体链接。资源缓冲区上限 250 条，溢出时丢弃的是新条目，请刷新页面后在视频开始播放时立即点击本书签");
notes.push("复制出的链接已内嵌来源页作为 Referer（#sgref= 片段，不会发给服务器）。若仍报 403，说明该站还需登录 Cookie，请在下载器「设置 → Cookie」导入");
var dk=window.matchMedia&&matchMedia("(prefers-color-scheme:dark)").matches;
var k=dk?{bg:"#1a1a1a",fg:"#e8e8e8",mu:"#9a9a9a",bd:"#3a3a3a",cd:"#242424",tg:"#3a3a3a"}:{bg:"#ffffff",fg:"#1a1a1a",mu:"#8a8a8a",bd:"#e5e5e5",cd:"#fafafa",tg:"#eaeaea"};
function el(t,s){var e=document.createElement(t);if(s)for(var p in s)e.style[p]=s[p];return e}
function tx(t,c,s){var e=el(t,s);e.textContent=c;return e}
var prev=document.getElementById?document.getElementById("sg-sniffer"):null;
if(prev&&prev.parentNode)prev.parentNode.removeChild(prev);
var host=el("div");host.id="sg-sniffer";
function panel(root){
var w=el("div",{position:"fixed",top:"16px",right:"16px",width:"460px",maxWidth:"calc(100vw - 32px)",maxHeight:"calc(100vh - 32px)",overflow:"auto",background:k.bg,color:k.fg,border:"1px solid "+k.bd,borderRadius:"12px",boxShadow:"0 8px 32px rgba(0,0,0,.25)",padding:"16px",font:"13px/1.6 -apple-system,system-ui,Segoe UI,sans-serif",boxSizing:"border-box",zIndex:2147483647});
root.appendChild(w);
var hd=el("div",{display:"flex",alignItems:"center",gap:"8px",marginBottom:"4px"});
hd.appendChild(tx("div","链接提取",{fontSize:"15px",fontWeight:"600",flex:"1"}));
var cl=el("button",{font:"inherit",fontSize:"12px",padding:"3px 10px",border:"1px solid "+k.bd,borderRadius:"6px",background:"transparent",color:"inherit",cursor:"pointer"});
cl.textContent="关闭";
cl.addEventListener("click",function(){if(host.parentNode)host.parentNode.removeChild(host)});
hd.appendChild(cl);w.appendChild(hd);
w.appendChild(tx("div","单击链接即全选后按 Ctrl+C；点「复制」可直接写入剪贴板",{fontSize:"12px",color:k.mu,marginBottom:"12px"}));
w.appendChild(tx("div","来源页（Referer）："+P,{fontSize:"12px",color:k.mu,wordBreak:"break-all",whiteSpace:"pre-wrap",marginBottom:"12px"}));
rows.forEach(function(g){
w.appendChild(tx("div",g[0]+"（"+g[1].length+"）",{fontSize:"11px",fontWeight:"600",letterSpacing:".04em",color:k.mu,margin:"16px 0 6px"}));
if(!g[1].length){w.appendChild(tx("div","无",{fontSize:"12px",color:k.mu,padding:"4px 0"}));return}
g[1].forEach(function(it){
var r=el("div",{display:"flex",gap:"8px",alignItems:"flex-start",background:k.cd,border:"1px solid "+k.bd,borderRadius:"8px",padding:"8px 10px",margin:"6px 0"});
r.appendChild(tx("span",it[0],{flex:"none",fontSize:"11px",fontWeight:"600",padding:"2px 7px",borderRadius:"4px",background:k.tg,color:k.fg}));
var b=el("div",{flex:"1",minWidth:"0",font:"11px/1.5 ui-monospace,Consolas,monospace",wordBreak:"break-all",whiteSpace:"pre-wrap",userSelect:"all",webkitUserSelect:"all",background:k.cd,color:k.fg,padding:"6px 8px",borderRadius:"6px",cursor:"text"});
b.textContent=pay(it[1]);
r.appendChild(b);
var cp=el("button",{flex:"none",font:"inherit",fontSize:"12px",padding:"3px 10px",border:"1px solid "+k.bd,borderRadius:"6px",background:"transparent",color:"inherit",cursor:"pointer"});
cp.textContent="复制";
cp.addEventListener("click",function(){
function pick(){try{var s=window.getSelection&&window.getSelection();if(!s)return false;s.removeAllRanges();s.selectAllChildren(b);return true}catch(e){return false}}
function fb(){cp.textContent="已选中";pick()}
pick();
try{navigator.clipboard.writeText(b.textContent).then(function(){cp.textContent="已复制"},fb)}catch(e){fb()}
});
r.appendChild(cp);w.appendChild(r);
});
});
notes.forEach(function(n){w.appendChild(tx("div",n,{fontSize:"12px",color:k.mu,marginTop:"10px",lineHeight:"1.5",whiteSpace:"pre-wrap"}))});
}
function plain(){
try{
var W=window.open("about:blank","_blank","width=560,height=640"),D=W.document;D.title="链接提取";
function f(t,c){var e=D.createElement(t);e.textContent=c;e.style.whiteSpace="pre-wrap";e.style.wordBreak="break-all";e.style.font="13px/1.7 ui-monospace,Consolas,monospace";D.body.appendChild(e)}
f("div","来源页（Referer）："+P);
rows.forEach(function(g){f("div","["+g[0]+" "+g[1].length+"]");g[1].forEach(function(it){f("div",pay(it[1]))})});
notes.forEach(function(n){f("div","["+n+"]")});
}catch(e){alert("覆盖层注入失败，请在开发者控制台粘贴脚本运行")}
}
var root=null;
try{root=host.attachShadow({mode:"open"})}catch(e){root=null}
if(!root)root=host;
var ok=false;
try{document.documentElement.appendChild(host);ok=true}catch(e){ok=false}
if(ok){panel(root)}else{plain()}
})();
