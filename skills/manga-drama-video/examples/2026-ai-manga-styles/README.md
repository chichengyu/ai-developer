# 2026 AI 漫剧风格映射示例

本示例展示如何把一条原创故事需求映射到 `references/2026-ai-manga-character-bank.md` 的爆款风格家族，并在 Step 4 写出可复用的人物 `prompt_fragment`。

## 风格家族速查

| 用户故事信号 | 风格家族 | 源模板 |
| --- | --- | --- |
| 盲眼少年 / 剑匣 / 水墨仙侠 / 逆天改命 | 水墨国风仙侠 | 李观棋 |
| 百世轮回 / 多人生线 / 市井与修真 | 百世轮回玄幻 | 陈默 |
| 弃子科举 / 朝堂权谋 / 清冷文人 | 素雅古风权谋 | 魏逆生 |
| 苗疆少主 / 甜宠 / 民俗艳丽 | 苗疆民俗甜宠 | 蚩衍 |
| 边关种田 / 双向救赎 / 烟火温柔 | 边关种田烟火 | 萧征 |
| 历史人物 / 汉代甲胄 / 连续剧悬念 | 历史国风剧场 | 韩信 |

## 示例：原创水墨仙侠

用户需求：“做一个盲眼少年背负剑匣、在雷雨中一剑断山的 9:16 写实动漫漫剧。”

Step 4 选择：

- 风格家族：李观棋 style（水墨国风仙侠）。
- Character style：写实动漫。
- 人物名字与设定改成原创，不复刻原剧角色。
- Prompt fragment 使用素材库第 1 条，并追加“雷雨、断山、一剑”等剧情元素。

```markdown
### 原创角色：沈无涯
- role: protagonist
- silhouette: 清瘦修长，左肩微倾，背负长方体剑匣
- signature_colors: #F5F0E6, #111111, #6B7B8C
- recurring_props: 黑布蒙眼、剑匣、断剑
- prompt_fragment: "2026 award-winning Chinese xianxia AI manga male lead, blind cold young swordsman, white plain robe, black blindfold, long ink-black hair, ancient sword box on his back, ink-wash mountain clouds and rain, hyper-real anime, sharp clean outlines 2-3px, lifelike skin with visible pores, cinematic three-point lighting, sword action full of flowing motion, no chibi, no plastic skin, no blurry edges"
- reference_image: 05_images/refs/shen_wuya.png
```

## 使用要求

- 先用素材库选定一个风格家族，不要在同一集混搭多个建模体系。
- 写实动漫模式必须保留“真实逼真 + 轮廓分明”。
- 用户选数字真人时，把 `hyper-real anime, sharp clean outlines` 换成 `photorealistic digital human, no anime outlines`。
- 素材库用于风格参考；不要直接复制原剧角色名、剧照或受版权保护的画面。
