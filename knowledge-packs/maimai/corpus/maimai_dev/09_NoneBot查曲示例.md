# NoneBot2与OneBot V11查曲插件示例

NoneBot插件是可加载的Python模块或包，在框架初始化后加载。事件响应器接收命令、提取参数，再调用独立业务函数；不要在模块导入时连接生产数据库或下载全量资源。[NoneBot插件说明](https://nonebot.dev/docs/tutorial/create-plugin)

## 本包可运行示例

examples/nonebot_song.py注册“舞萌查曲”命令，前缀由机器人的COMMAND_START决定；默认配置通常使用/。它从本包data/songs.json读公开资料，支持曲名、落雪ID和别名，最多返回五首候选。它是独立演示，不自动装进ナナセ，也不会同步玩家成绩。

使用已安装NoneBot2与OneBot V11适配器的机器人，在入口初始化后添加：

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path('./maimai-knowledge/examples').resolve()))
nonebot.load_plugin('nonebot_song')
```

按实际部署目录调整路径，保留包内scripts/data相对位置。ナナセ已接入知识库时，日常自然语言查曲可直接走知识库；只有需要固定确定性命令才额外加载这个示例。

## 原创实现选择

文件读取放到线程，避免阻塞事件循环；业务查找不依赖QQ对象，方便离线测试；标题、别名等源站文本使用MessageSegment.text发送，不当作CQ字符串解释。参数过长或为空时返回明确格式，多义别名保留候选。

真实部署如要加群白名单，应在handler调用业务前统一校验；公开曲库权限与个人成绩授权分开。不要在示例里硬编码机器人管理员、服务器地址、玩家ID或访问密钥，也不要把“源数据存在”变成写账号状态的命令。

参考：[OneBot消息段规范](https://github.com/botuniverse/onebot-11/blob/master/message/segment.md)。
