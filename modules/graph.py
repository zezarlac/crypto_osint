"""
modules/graph.py - CryptoWalletOSINT
3 visualization formats:
  1. visualize_hierarchical()  - concentric-ring PNG
  2. export_interactive_html() - D3.js force graph with click-to-inspect
  3. export_sankey_html()      - ribbon flow diagram, pure D3 v7 core only
"""
import json, os, math, networkx as nx
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from modules.utils import extract_edges
from modules.screening import Screener

_HOP_COLORS = {0:"#ef4444",1:"#6366f1",2:"#22d3ee",3:"#f59e0b"}
_FLAG_BORDER = "#facc15"

def _wrap_address(addr, width=21):
    if not addr or len(addr) <= width: return addr
    return "\n".join(addr[i:i+width] for i in range(0,len(addr),width))

class TransactionGraph:
    def __init__(self, wallet_data, depth=1):
        self.data=wallet_data; self.depth=depth; self.G=nx.DiGraph()
        self.target=wallet_data.get("address",""); self.chain=wallet_data.get("chain","")
        self.screener=Screener()

    def build(self):
        self.G.add_node(self.target,kind="target",hop=0)
        self._screen_and_tag(self.target)
        edges=extract_edges(self.target,self.data,hop=1)
        for e in edges:
            for node in (e["from"],e["to"]):
                if node not in self.G:
                    self.G.add_node(node,kind="related",hop=1); self._screen_and_tag(node)
            self.G.add_edge(e["from"],e["to"],txid=e["txid"],value=e.get("value",0),hop=1)

    @classmethod
    def from_trace(cls, trace_result):
        g=cls.__new__(cls); g.data={}
        g.target=trace_result.get("target",""); g.chain=trace_result.get("chain","")
        g.depth=trace_result.get("depth",1); g.G=nx.DiGraph(); g.screener=Screener()
        for addr,meta in trace_result.get("nodes",{}).items():
            hop=meta.get("hop",1)
            g.G.add_node(addr,kind="target" if hop==0 else "related",hop=hop)
            if meta.get("flagged"): g.G.nodes[addr]["flagged"]=meta["flagged"]
        for e in trace_result.get("edges",[]):
            frm,to=e["from"],e["to"]
            for node in (frm,to):
                if node not in g.G: g.G.add_node(node,kind="related",hop=e.get("hop",1))
            g.G.add_edge(frm,to,txid=e.get("txid","?"),value=e.get("value",0),hop=e.get("hop",1))
        return g

    def _screen_and_tag(self,address):
        match=self.screener.check(address)
        if match: self.G.nodes[address]["flagged"]=match

    # ── 1. HIERARCHICAL PNG ────────────────────────────────────
    def visualize_hierarchical(self, output_name="wallet", out_dir="."):
        if not self.G.nodes: return ""
        n=len(self.G.nodes)
        fig_w=max(18,min(32,12+n*0.7)); fig_h=max(12,min(22,8+n*0.5))
        fig,ax=plt.subplots(figsize=(fig_w,fig_h))
        fig.patch.set_facecolor("#0d0d1a"); ax.set_facecolor("#0d0d1a")
        pos={self.target:(0,0)}; hops={}
        for nd in self.G.nodes():
            h=self.G.nodes[nd].get("hop",1); hops.setdefault(h,[]).append(nd)
        for hop in sorted(hops.keys()):
            if hop==0: continue
            for i,nd in enumerate(hops[hop]):
                r=2.5+(hop-1)*3.5; a=2*math.pi*i/max(len(hops[hop]),1)
                pos[nd]=(r*math.cos(a),r*math.sin(a))
        nx.draw_networkx_edges(self.G,pos,edge_color="#94a3b8",arrows=True,arrowsize=16,
                               alpha=0.45,width=1.0,ax=ax,connectionstyle="arc3,rad=0.08")
        nodelist=list(self.G.nodes())
        colors=[_HOP_COLORS.get(self.G.nodes[nd].get("hop",1),"#6366f1") for nd in nodelist]
        sizes=[2400 if nd==self.target else 700-(self.G.nodes[nd].get("hop",1)-1)*100 for nd in nodelist]
        ec=[_FLAG_BORDER if self.G.nodes[nd].get("flagged") else "#0d0d1a" for nd in nodelist]
        lw=[2.8 if self.G.nodes[nd].get("flagged") else 0.5 for nd in nodelist]
        nx.draw_networkx_nodes(self.G,pos,nodelist=nodelist,node_color=colors,node_size=sizes,
                               alpha=0.95,ax=ax,edgecolors=ec,linewidths=lw)
        labels={}
        for nd in nodelist:
            attrs=self.G.nodes[nd]; w=_wrap_address(nd)
            if nd==self.target: w+="\n\u25b6 TARGET"
            if attrs.get("flagged"): w+=f"\n\u26a0 {attrs['flagged'].get('entity','FLAGGED')}"
            labels[nd]=w
        nx.draw_networkx_labels(self.G,pos,labels,font_size=5.5,font_color="#e2e8f0",
                                font_family="monospace",ax=ax,
                                bbox=dict(facecolor="#13131f",edgecolor="#3730a3",
                                         boxstyle="round,pad=0.25",alpha=0.85,linewidth=0.6))
        lh=[mpatches.Patch(color=_HOP_COLORS[0],label="Target"),
            mpatches.Patch(color=_HOP_COLORS[1],label="Hop 1")]
        if self.depth>=2: lh.append(mpatches.Patch(color=_HOP_COLORS[2],label="Hop 2"))
        if self.depth>=3: lh.append(mpatches.Patch(color=_HOP_COLORS[3],label="Hop 3"))
        if any(self.G.nodes[nd].get("flagged") for nd in nodelist):
            lh.append(mpatches.Patch(facecolor="#1e1e3f",edgecolor=_FLAG_BORDER,linewidth=2.5,label="\u26a0 Flagged"))
        ax.legend(handles=lh,facecolor="#1e1e3f",labelcolor="white",loc="upper left",fontsize=8)
        fn=sum(1 for nd in nodelist if self.G.nodes[nd].get("flagged"))
        wt=f"  \u00b7  \u26a0 {fn} flagged" if fn else ""
        ax.set_title(f"Hierarchical  |  {self.chain.upper()}  |  depth={self.depth}\n{self.target}\n{n} nodes \u00b7 {len(self.G.edges)} edges{wt}",
                     color="white",fontsize=9,pad=14,family="monospace")
        ax.axis("off"); plt.tight_layout()
        os.makedirs(out_dir,exist_ok=True)
        fname=os.path.join(out_dir,f"graph_hierarchical_{self.target[:10]}.png")
        plt.savefig(fname,dpi=140,bbox_inches="tight",facecolor=fig.get_facecolor())
        plt.close(); return fname

    # ── 2. INTERACTIVE D3.JS HTML ─────────────────────────────
    def export_interactive_html(self, output_dir="."):
        data=nx.node_link_data(self.G)
        for node in data["nodes"]:
            attrs=self.G.nodes[node["id"]]
            node["hop"]=attrs.get("hop",1); node["flagged"]=bool(attrs.get("flagged"))
            if attrs.get("flagged"): node["entity"]=attrs["flagged"].get("entity","")
        dj=json.dumps(data); tgt=json.dumps(self.target)
        # Build as string concat to avoid brace conflicts with JS
        H = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        H += '<meta name="viewport" content="width=device-width">'
        H += '<title>Interactive Graph</title>'
        H += '<script src="https://d3js.org/d3.v7.min.js"></script>'
        H += '<style>'
        H += 'body{background:#0d0d1a;color:#e2e8f0;margin:0;padding:10px;font-family:Segoe UI}'
        H += '#container{width:100%;height:100vh}'
        H += 'svg{background:#0d0d1a;border:1px solid #1e1b4b;border-radius:8px}'
        H += '#info,#ctrl{position:absolute;background:#13131f;border:1px solid #1e1b4b;'
        H += 'padding:12px;border-radius:8px;font-size:12px;z-index:10}'
        H += '#info{top:10px;left:10px;max-width:360px}'
        H += '#ctrl{bottom:10px;left:10px}'
        H += 'button{background:#312e81;color:#a5b4fc;border:1px solid #3730a3;'
        H += 'padding:6px 12px;border-radius:4px;cursor:pointer;margin:2px;font-size:11px}'
        H += 'button:hover{background:#3730a3}'
        H += '.node{cursor:pointer}'
        H += '.flagged{stroke:#facc15!important;stroke-width:2.5px!important}'
        H += '.lnk{stroke:#94a3b8;stroke-opacity:0.5}'
        H += 'text{pointer-events:none;font-size:8px;fill:#e2e8f0;font-family:monospace}'
        H += '#af{font-family:monospace;font-size:10px;word-break:break-all;color:#a5b4fc;margin-top:4px;line-height:1.5}'
        H += '.hb{display:inline-block;padding:1px 7px;border-radius:8px;font-size:10px;margin-top:4px}'
        H += '.fb{color:#facc15;font-weight:600;margin-top:4px}'
        H += '</style></head><body>'
        H += '<div id="container"><svg id="graph"></svg></div>'
        H += '<div id="info"><strong style="color:#818cf8">\U0001f50d Click a node to inspect</strong>'
        H += '<div id="si" style="margin-top:8px"></div></div>'
        H += '<div id="ctrl">Filter: '
        H += '<select id="hf" style="background:#312e81;color:#a5b4fc;border:1px solid #3730a3;padding:4px">'
        H += '<option value="">All hops</option><option value="1">\u2264 1 hop</option>'
        H += '<option value="2">\u2264 2 hops</option><option value="3">\u2264 3 hops</option>'
        H += '</select><button onclick="rz()">Reset Zoom</button></div>'
        H += '<script>'
        H += 'const data=' + dj + ';'
        H += 'const TGT=' + tgt + ';'
        H += r"""
const HC=["#ef4444","#6366f1","#22d3ee","#f59e0b"];
const hc=h=>HC[h]||"#6366f1";
const HL={0:"Target",1:"Hop 1",2:"Hop 2",3:"Hop 3"};
const HB={0:"#450a0a",1:"#1e1b4b",2:"#0c2e33",3:"#1c1000"};
const W=window.innerWidth-20,H2=window.innerHeight-20;
const svg=d3.select("#graph").attr("width",W).attr("height",H2);
const g=svg.append("g");
svg.call(d3.zoom().on("zoom",e=>g.attr("transform",e.transform)));
const sim=d3.forceSimulation(data.nodes)
  .force("link",d3.forceLink(data.links).id(d=>d.id).distance(70))
  .force("charge",d3.forceManyBody().strength(-320))
  .force("center",d3.forceCenter(W/2,H2/2))
  .force("col",d3.forceCollide().radius(18));
const lnk=g.selectAll(".lnk").data(data.links).enter()
  .append("line").attr("class","lnk").attr("stroke","#94a3b8").attr("stroke-width",1.5);
const nd=g.selectAll(".node").data(data.nodes).enter()
  .append("circle").attr("class",d=>"node"+(d.flagged?" flagged":""))
  .attr("r",d=>d.id===TGT?14:7).attr("fill",d=>hc(d.hop))
  .attr("stroke",d=>d.flagged?"#facc15":"#0d0d1a").attr("stroke-width",d=>d.flagged?2.5:1.5)
  .on("click",(e,d)=>{
    const badge='<div class="hb" style="background:'+(HB[d.hop]||"#1e1b4b")+';color:'+hc(d.hop)+'">'+(HL[d.hop]||"Hop "+d.hop)+'</div>';
    const flag=d.flagged?'<div class="fb">\u26a0 '+d.entity+'</div>':"";
    const id_esc=d.id.replace(/'/g,"\\'");
    const btn='<button onclick="navigator.clipboard.writeText(\''+id_esc+'\').then(()=>this.textContent=\'\u2713 Copied\').catch(()=>{})" style="margin-top:6px;font-size:10px;padding:3px 8px">Copy address</button>';
    document.getElementById("si").innerHTML=badge+flag+'<div id="af">'+d.id+'</div>'+btn;
  })
  .call(d3.drag()
    .on("start",e=>{if(!e.active)sim.alphaTarget(0.3).restart();e.subject.fx=e.x;e.subject.fy=e.y;})
    .on("drag",e=>{e.subject.fx=e.x;e.subject.fy=e.y;})
    .on("end",e=>{if(!e.active)sim.alphaTarget(0);e.subject.fx=null;e.subject.fy=null;}));
const lbl=g.selectAll(".lbl").data(data.nodes).enter()
  .append("text").attr("text-anchor","middle").attr("dy",".3em")
  .text(d=>d.id.substring(0,6)+"\u2026"+d.id.slice(-4));
sim.on("tick",()=>{
  lnk.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y).attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  nd.attr("cx",d=>d.x).attr("cy",d=>d.y);
  lbl.attr("x",d=>d.x).attr("y",d=>d.y);
});
document.getElementById("hf").addEventListener("change",e=>{
  const f=e.target.value?parseInt(e.target.value):null;
  nd.style("opacity",d=>!f||d.hop<=f?1:0.1);
  lnk.style("opacity",d=>!f||(d.source.hop<=f&&d.target.hop<=f)?0.5:0.05);
});
function rz(){svg.transition().duration(750).call(d3.zoom().transform,d3.zoomIdentity.translate(W/2,H2/2).scale(1));}
"""
        H += '</script></body></html>'
        os.makedirs(output_dir,exist_ok=True)
        path=os.path.join(output_dir,f"graph_interactive_{self.target[:10]}.html")
        with open(path,"w",encoding="utf-8") as f: f.write(H)
        return path

    # ── 3. SANKEY / RIBBON FLOW HTML (pure D3 v7 core, no plugins) ──
    def export_sankey_html(self, output_dir="."):
        nodes_list=list(self.G.nodes()); node_idx={n:i for i,n in enumerate(nodes_list)}
        sn=[]
        for n in nodes_list:
            a=self.G.nodes[n]; fl=a.get("flagged")
            sn.append({"id":node_idx[n],
                       "name":(n[:12]+"\u2026"+n[-6:]) if n!=self.target else "TARGET",
                       "fullAddr":n,"hop":a.get("hop",1),
                       "flagged":bool(fl),"entity":fl.get("entity","") if fl else ""})
        sl=[{"source":node_idx[src],"target":node_idx[dst],
             "value":max(0.01,d.get("value",0.01)),"txid":d.get("txid","?")}
            for src,dst,d in self.G.edges(data=True)]
        nj=json.dumps(sn); lj=json.dumps(sl)
        H  = '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        H += '<title>Money Flow</title>'
        H += '<script src="https://d3js.org/d3.v7.min.js"></script>'
        H += '<style>'
        H += '*{box-sizing:border-box;margin:0;padding:0}'
        H += 'body{background:#0d0d1a;color:#e2e8f0;font-family:Segoe UI;padding:20px}'
        H += 'h2{color:#a5b4fc;font-size:18px;margin-bottom:4px}'
        H += '.sub{font-size:11px;color:#64748b;font-family:monospace;word-break:break-all;margin-bottom:16px}'
        H += 'svg{display:block;overflow:visible}'
        H += '.ribbon{transition:fill-opacity .18s}'
        H += '.ribbon:hover{fill-opacity:.75!important}'
        H += '#tip{position:fixed;display:none;pointer-events:none;background:#13131f;'
        H += 'border:1px solid #1e1b4b;border-radius:6px;padding:8px 12px;font-size:11px;'
        H += 'font-family:monospace;word-break:break-all;max-width:340px;z-index:99;line-height:1.55}'
        H += '.leg{display:inline-flex;align-items:center;gap:6px;margin-right:18px;font-size:11px}'
        H += '.ld{width:12px;height:12px;border-radius:3px;flex-shrink:0}'
        H += '</style></head><body>'
        H += '<h2>\U0001f4b0 Money Flow Diagram</h2>'
        H += '<div class="sub">' + self.target + '</div>'
        H += '<div id="tip"></div><svg id="flow"></svg>'
        H += '<div id="leg" style="margin-top:14px"></div>'
        H += '<script>'
        H += 'const NODES=' + nj + ';'
        H += 'const LINKS=' + lj + ';'
        H += r"""
const HC=["#ef4444","#6366f1","#22d3ee","#f59e0b"];
const hc=h=>HC[h]||"#6366f1";
const NW=18,PAD=22,ML=20,MR=270,MT=30,MB=50;
const numCols=Math.max(...NODES.map(n=>n.hop))+1;
const perCol=Array.from({length:numCols},()=>[]);
NODES.forEach(n=>perCol[n.hop].push(n));
const maxR=Math.max(...perCol.map(c=>c.length));
const H2=Math.max(480,maxR*52+(maxR-1)*PAD+MT+MB);
const W=Math.min(window.innerWidth-40,1200);
const aW=W-ML-MR-NW, aH=H2-MT-MB;
const svg=d3.select("#flow").attr("width",W).attr("height",H2);
const g=svg.append("g").attr("transform","translate("+ML+","+MT+")");
const tip=document.getElementById("tip");
function cx(i){return numCols===1?aW/2:(i/(numCols-1))*aW;}
const oV=new Array(NODES.length).fill(0);
const iV=new Array(NODES.length).fill(0);
LINKS.forEach(l=>{oV[l.source]+=l.value;iV[l.target]+=l.value;});
const nV=NODES.map((_,i)=>Math.max(oV[i],iV[i],0.01));
perCol.forEach((col,hop)=>{
  col.sort((a,b)=>nV[b.id]-nV[a.id]);
  const tot=col.reduce((s,n)=>s+nV[n.id],0);
  const bud=aH-PAD*Math.max(col.length-1,0);
  let y=0;
  col.forEach(n=>{
    const h=Math.max(20,(nV[n.id]/tot)*bud);
    n.x0=cx(hop);n.x1=n.x0+NW;n.y0=y;n.y1=y+h;y+=h+PAD;
  });
});
const sO=new Array(NODES.length).fill(0);
const tO=new Array(NODES.length).fill(0);
LINKS.forEach(l=>{
  const s=NODES[l.source],t=NODES[l.target];
  if(!s||!t||s.x0===undefined||t.x0===undefined)return;
  const sw=Math.max(1.5,(l.value/nV[l.source])*(s.y1-s.y0));
  const tw=Math.max(1.5,(l.value/nV[l.target])*(t.y1-t.y0));
  const ys=s.y0+sO[l.source],yt=t.y0+tO[l.target];
  sO[l.source]+=sw;tO[l.target]+=tw;
  const x0=s.x1,x1=t.x0,mx=(x0+x1)/2;
  const p=["M"+x0+" "+ys,"C"+mx+" "+ys+","+mx+" "+yt+","+x1+" "+yt,
            "L"+x1+" "+(yt+tw),"C"+mx+" "+(yt+tw)+","+mx+" "+(ys+sw)+","+x0+" "+(ys+sw),"Z"].join(" ");
  g.append("path").attr("class","ribbon").attr("d",p)
   .attr("fill",hc(Math.max(s.hop,t.hop))).attr("fill-opacity",0.42)
   .on("mousemove",e=>{
     tip.style.display="block";tip.style.left=(e.clientX+14)+"px";tip.style.top=(e.clientY-10)+"px";
     tip.innerHTML="<strong>Transfer</strong><br>From: "+s.fullAddr+"<br>To: "+t.fullAddr+"<br>Value: "+l.value.toFixed(6);
   }).on("mouseleave",()=>tip.style.display="none");
});
NODES.forEach(n=>{
  if(n.x0===undefined)return;
  const h=Math.max(2,n.y1-n.y0),gr=g.append("g");
  gr.append("rect").attr("x",n.x0).attr("y",n.y0).attr("width",NW).attr("height",h)
    .attr("fill",hc(n.hop)).attr("rx",3)
    .attr("stroke",n.flagged?"#facc15":"none").attr("stroke-width",n.flagged?2.5:0)
    .on("mousemove",e=>{
      tip.style.display="block";tip.style.left=(e.clientX+14)+"px";tip.style.top=(e.clientY-10)+"px";
      tip.innerHTML=(n.flagged?"<span style='color:#facc15'>\u26a0 "+n.entity+"</span><br>":"")
        +"<strong>"+n.name+"</strong><br>"+n.fullAddr;
    }).on("mouseleave",()=>tip.style.display="none");
  gr.append("text").attr("x",n.x1+8).attr("y",n.y0+h/2).attr("dy","0.35em")
    .attr("fill",n.flagged?"#facc15":"#e2e8f0").style("font-size","10px").style("font-family","monospace")
    .text(n.name+(n.flagged?"\u2002\u26a0 "+n.entity:""));
});
[...Array(numCols).keys()].forEach(h=>{
  g.append("text").attr("x",cx(h)+NW/2).attr("y",-10).attr("text-anchor","middle")
   .attr("fill",hc(h)).style("font-size","11px").style("font-weight","600")
   .text(h===0?"TARGET":"Hop "+h);
});
const le=document.getElementById("leg");
[...Array(numCols).keys()].forEach(h=>{
  le.innerHTML+='<span class="leg"><span class="ld" style="background:'+hc(h)+'"></span>'+(h===0?"Target":"Hop "+h)+"</span>";
});
le.innerHTML+='<span class="leg"><span class="ld" style="background:none;border:2px solid #facc15"></span>Flagged</span>';
"""
        H += '</script></body></html>'
        os.makedirs(output_dir,exist_ok=True)
        path=os.path.join(output_dir,f"graph_sankey_{self.target[:10]}.html")
        with open(path,"w",encoding="utf-8") as f: f.write(H)
        return path

    # ── Stats & Export ─────────────────────────────────────────
    def get_stats(self):
        top5=sorted(self.G.degree(),key=lambda x:x[1],reverse=True)[:5]
        flagged={nd:self.G.nodes[nd]["flagged"] for nd in self.G.nodes if self.G.nodes[nd].get("flagged")}
        return {"nodes":len(self.G.nodes),"edges":len(self.G.edges),
                "unique_addresses":list(self.G.nodes),"most_connected":top5,"flagged":flagged}

    def export_json(self, path="graph.json"):
        data=nx.node_link_data(self.G)
        with open(path,"w") as f: json.dump(data,f,indent=2,default=str)
        return path
