# Character Styles

Pick **one** character style per story and paste the matching block into `04_art_direction.md` under "Character style". Use `scene.character_style_override` in `02_script.md` to swap per scene (e.g. one scene with a real person on the phone).

---

## 1. 写实动漫 (default — hyper-real anime)

**Look**
Modern cinematic anime with photoreal-leaning rendering. Crisp black outlines 2-3 px wide (kept consistent across all shots). Skin has subsurface scattering, pores, and subtle makeup; eyes retain anime proportions but with realistic iris detail and catchlights. Hair strands are individually rendered. No moe-blush, no chibi, no super-deformed proportions.

**Lighting**
Three-point cinematic lighting with a strong key (often off-camera 45 degrees), soft fill, and rim light that separates the character from the background. Practical lights in scene (neon, lamps, screens) also contribute. Avoid flat anime lighting.

**Prompt fragment (paste verbatim into every character block)**
> hyper-real anime character, sharp clean outlines 2-3px, lifelike skin with subsurface scattering and visible pores, cinematic three-point lighting, modern anime proportions with realistic eye iris detail and catchlights, individual hair strands, no chibi, no super-deformed proportions

**Do / Don't**
- Do: keep outlines crisp, lock seed per character, use reference sheet.
- Don't: drop the outline on close-ups, drift toward chibi or moe-blush, switch to cel-shading.

---

## 2. 数字真人 (photoreal digital human)

**Look**
Photoreal AI-generated human, indistinguishable from a real photograph or a high-end talking-head model. No anime outlines, no stylization. Skin texture, pores, fine hair, blemishes all preserved.

**Lighting**
Naturalistic lighting: soft daylight, practical lamps, screen light. Match the lighting direction implied by the setting. Avoid over-stylized rim lights unless the scene is a club or concert.

**Prompt fragment**
> photorealistic digital human, ultra-detailed skin with pores and fine hair, no stylization, no anime outlines, no cel-shading, cinematic natural lighting, 85mm lens look, shallow depth of field

**Provider pairing**
For talking-head scenes, pair with `references/digital-human-options.md`: SadTalker, LivePortrait, Hallo, D-ID, HeyGen, or MuseTalk. Generate the still portrait here, then drive lip sync in Step 8.

**Do / Don't**
- Do: lock reference face, sample multiple angles, use high-quality face crops.
- Don't: add anime outlines, swap to anime style mid-video, crop too tight on neck/shoulders.

---

## 3. 经典动漫 (classic anime)

**Look**
Classic 90s/2000s anime: cel-shaded, big expressive eyes, soft hair shapes, simple but readable silhouettes. Painterly backgrounds. Limited animation feel even on stills.

**Prompt fragment**
> classic anime character, cel-shaded with flat color fills, big expressive eyes, soft painterly hair shapes, painterly background, warm film grain

**Do / Don't**
- Do: keep color fills flat, keep line work confident.
- Don't: add photoreal skin, switch to 写实动漫 mid-story.

---

## 4. 半写实 (semi-real blend)

**Look**
A blend: character face is photoreal, body and clothing stay stylized, backgrounds are semi-painterly. Common in modern anime films and high-end commercials.

**Prompt fragment**
> semi-real character, photoreal face and hands, stylized clothing and hair, painterly background with realistic lighting, cinematic widescreen 16:9

**Do / Don't**
- Do: keep the face photoreal, the body stylized.
- Don't: drift fully into 写实动漫 or 经典动漫 mid-story.

---

## 5. 2026 AI漫剧男主系 (爆款男主模板)

Source: `references/2026-ai-manga-character-bank.md`. Use when the user wants the visual family of 2026 爆款 AI 漫剧男主 (李观棋 / 陈默 / 魏逆生 / 蚩衍 / 萧征 / 韩信).

**Look**
The default 写实动漫 pipeline with 2026 platform-grade quality: lifelike skin with pores, subtle texture, and strong cinematic light; clean 2-3px outlines; distinct face shapes instead of a reused template face; wardrobe, hair, and props carry genre DNA (水墨仙侠, 百世轮回, 素雅权谋, 苗疆甜宠, 边关种田, 历史国风). No chibi, no plastic skin, no blurry edges.

**Lighting**
Three-point cinematic lighting with genre-specific practical sources: ink-wash mist for xianxia, candlelight for court, warm golden hour for frontier, glamour light for Miao romance.

**Prompt fragment**
> 2026 AI manga character, hyper-real anime, sharp clean outlines 2-3px, lifelike skin with visible pores, distinct face shape, cinematic three-point lighting, genre-specific wardrobe and props, no chibi, no plastic skin, no template idol face

**数字真人 override**
If the user selects 数字真人 for this template, replace the fragment with:
> photorealistic digital human, ultra-detailed skin, distinct face shape, natural cinematic lighting, no anime outlines, no stylization

**Do / Don't**
- Do: keep real skin texture, lock one face, vary face geometry, keep outlines sharp in 写实动漫 mode.
- Don't: use the same face for every male lead, over-polish skin, lose outlines in close-ups, switch styles mid-video.

---

## 6. 3D 国风动漫 (国漫仙侠 CG)

Source: `references/3d-guofeng-xianxia-prompts.md`. Use when the user asks for 3D 国风动漫 / 国漫仙侠 / 高质量仙侠人物场景角色提示词，或明确说出文章里的仙侠模板。

**Look**
Next-gen 3D Chinese fantasy: PBR materials, real cloth and hair simulation, volumetric light, cinematic depth of field, high-detail 8K rendering. Characters keep realistic skin and clean face edges. The original article's universal terms must be appended to every prompt:

> 3D国风动漫，国漫玄幻风格，CG电影渲染，次世代建模，PBR真实材质，真实布料与发丝物理模拟，体积光，HDR电影级光影，电影景深，高细节，8K超清，大制作质感

And the consistency block must be appended to every recurring character shot:

> 角色人设锁定，每张图保持同一张脸，同一套服装，同一人物设定，连续人物动态，电影级渲染，统一建模，统一风格

**Prompt fragment**
> 3D国风动漫, 国漫玄幻风格, CG电影渲染, 次世代建模, PBR真实材质, hyper-real skin texture, visible pores, clean sharp face edges, no plastic skin, no flat anime shading, 体积光, 电影级光影, HDR光照, 电影景深, 8K超清

**数字真人 override**
If the user selects 数字真人, replace the 3D CG terms with:
> photorealistic digital human, ultra-detailed skin, natural cinematic lighting, no anime outlines, no stylization

**Do / Don't**
- Do: keep PBR materials, cloth/hair simulation, consistent character model, realistic skin, sharp face edges.
- Don't: mix 3D CG with 写实动漫/数字真人 in one project, omit consistency terms, let faces drift.
