# maidata.txt与simai格式入门

simai是社区文本谱面记法，maidata.txt常同时含元数据与多个难度谱面；它不是SEGA官方源码。基础写法包括BPM的(120)、分割的{4}、TAP位置数字、逗号推进时间与E结束。时长可按240/BPM/分割数计算。[simai规范](https://w.atwiki.jp/simai/pages/1003.html)

## 原创最小例子

以下是为讲解自构的空音乐练习，不对应任何商业歌曲：

```text
&title=Original Timing Exercise
&artist=Local Example
&first=0
&lv_1=1
&inote_1=(120){4}1,2/3,,(240)4,E
```

在示例的定义下，1号TAP在0秒，2/3号同时在0.5秒，空拍后4号在1.5秒；最后一步按240BPM四分音符推进，结束时间1.75秒。示例程序examples/simai_timing.py只演示这部分时序，主动拒绝HOLD、SLIDE、TOUCH等不支持语法。

## 实际格式的复杂部分

完整解析器还需要元数据、多难度、注释、HOLD时长、滑条形状与独立等待、多条及连接轨迹、TOUCH、BREAK/EX修饰、等效BPM、绝对秒时长和方言扩展。不同模拟器支持范围不同，要按它所声称的规范版本验证，不能只用正则把所有逗号切开就声称完整兼容。

应区分语法合法、时序正确、几何可画和双手可打四层验证。一个合法字符串不保证可用两只手完成。完整项目可参考[MaiLib作者说明](https://github.com/Neskol/MaiLib)；它的MA2/Simai支持描述属于该项目实现，不是本包内置能力。

自制谱应使用有权使用的音频与原创谱面。本包仅附原创短例子，不批量复制现成商业谱面文本。
