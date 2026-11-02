"""Optional real-plugin/NoneBot/MCP offline integration check, no external IO."""
import argparse
import asyncio
from collections import Counter
import json
import math
from pathlib import Path
import site
import sys

from packlib import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plugin-project',type=Path,help='Path containing nonebot_plugin_soruto_ai')
    parser.add_argument('--extra-site',type=Path,help='Optional isolated SDK dependency directory')
    args=parser.parse_args()
    if args.extra_site:site.addsitedir(str(args.extra_site.resolve()))
    if args.plugin_project:sys.path.insert(0,str(args.plugin_project.resolve()))
    from nonebot_plugin_soruto_ai.core import knowledge as k
    k._rows=[(p.relative_to(ROOT/'corpus').parts[0],p.name,i,text)
             for p in sorted((ROOT/'corpus').rglob('*.md'))
             for i,text in enumerate(k.chunks(p.read_text(encoding='utf-8')))]
    k._index=[Counter(k.tokens(r[3])) for r in k._rows]
    frequency=Counter(term for item in k._index for term in item)
    k._idf={term:math.log(1+(len(k._rows)-count+.5)/(count+.5)) for term,count in frequency.items()}
    k._average_length=sum(sum(item.values()) for item in k._index)/len(k._index)
    cases={
        'AP+和DX分满分有什么区别':'06_判定与成绩标记.md',
        '13.7定数100.5单曲Rating':'09_Rating计算与评级.md',
        'ナナセ凌晨会主动聊天吗':'01_ナナセ架构.md',
        '星星头和滑条何时出发':'03_滑条与读谱.md',
        'Oshama Scramble!':'maimai_songs/',
        '真爱歌':'generated-songs-001.md',
        '水鱼OAuth':'04_公开接口与授权.md',
    }
    report={'bm25':{}}
    for query,expected in cases.items():
        results=k._rank(query,4)
        assert any(expected in item for item in results),(query,results)
        report['bm25'][query]=[r.split(']')[0]+']' for r in results]
    import nonebot
    nonebot.init(_env_file=None)
    sys.path.insert(0,str(ROOT/'examples'))
    plugin=nonebot.load_plugin('nonebot_song')
    assert plugin is not None and len(plugin.matcher)==1
    report['nonebot_example']='loaded one matcher; no bot connection or startup IO'
    report['mcp']=asyncio.run(check_mcp(args.extra_site))
    (ROOT/'docs').mkdir(exist_ok=True)
    (ROOT/'docs/integration-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


async def check_mcp(extra_site):
    from nonebot_plugin_soruto_ai.config import Config,MCPServer
    from nonebot_plugin_soruto_ai.core import config,tools
    from nonebot_plugin_soruto_ai.models import Chat,Message,User
    helper=ROOT/'examples/mcp_server.py'
    # Child process adds isolated dependencies AFTER the base environment.
    code='import site,runpy; '
    if extra_site:code+=f'site.addsitedir({str(extra_site.resolve())!r}); '
    code+=f'runpy.run_path({str(helper)!r},run_name="__main__")'
    old=config.SETTINGS
    config.init(Config(soruto_enable_tools=True,soruto_mcp_servers={
        'maimai':MCPServer(transport='stdio',command=sys.executable,args=['-c',code],
                          allowed_tools=['search_song'],readonly_tools=['search_song'])}))
    registry=tools.Registry()
    try:
        await registry.initialize()
        assert not registry.unavailable,registry.unavailable
        external=[tool for tool in registry.tools.values() if tool.server]
        assert len(external)==1 and external[0].remote_name=='search_song'
        message=Message(Chat('999:private:42','private'),User(42,'offline'),1,'test',None)
        result=await registry.execute(external[0].name,{'query':'真爱歌'},message)
        assert 'True Love Song' in result and '8' in result,result
        workers=list(registry.workers.values())
    finally:
        await registry.close()
        config.init(old)
    assert workers and all(worker.task.done() for worker in workers)
    return 'real SDK stdio: discover search_song, query alias, close all workers'


if __name__=='__main__':
    main()
