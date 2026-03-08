# mahjong-cpp 最终接入方式

1. 这台机器已经装好可用环境：`MSYS2 + UCRT64 + Boost + CMake + Ninja`。
2. 如果别的机器要复现，最短安装路线：
3. `winget install MSYS2.MSYS2`
4. 在 `MSYS2 UCRT64` 里执行：
5. `pacman -Syu`
6. 重开后执行：
7. `pacman -S --needed mingw-w64-ucrt-x86_64-toolchain mingw-w64-ucrt-x86_64-boost mingw-w64-ucrt-x86_64-cmake mingw-w64-ucrt-x86_64-ninja mingw-w64-ucrt-x86_64-rapidjson mingw-w64-ucrt-x86_64-spdlog`
8. 进入算法目录：
9. `cd /d/PROJECT/VSCode/AI+Game/AI_Mahjong/Algorithm/mahjong-cpp-master`
10. 配置并编译：
11. `cmake -S . -B build-ucrt-app -G Ninja -DBUILD_TEST=OFF`
12. `cmake --build build-ucrt-app -j 8`
13. 现在推荐直接启动：
14. `start_all.bat`
15. 如果只想单独启动算法端：
16. `Algorithm\mahjong-cpp-master\run_server_ucrt.bat`
17. 这两个入口最终都会走 `tools/launchers/algorithm_backend_launcher.py`，由它直接监督 `nanikiru.exe`，不再依赖旧的 `bash -> nanikiru.exe` 长链路。
18. 当前已验证该目录下有：
19. `nanikiru.exe`、`request_schema.json`、`suits_patterns.json`、`honors_patterns.json`、`uradora.bin`
20. Crawler 侧只需要调用 `Crawler/mahjong_cpp_client.py`。
21. 最小字段：
22. `hand`, `melds`, `dora_indicators`, `round_wind`, `seat_wind`, `version`
23. 建议额外传：
24. `wall`
23.
24. 最小调用示例：
25. ```python
26. from mahjong_cpp_client import build_request, request_recommendation, rank_stats
27.
28. payload = build_request(
29.     hand=["2m","2m","2m","5m","6m","7m","3p","4p","5p","3s","3s","3s","2z","2z"],
30.     melds=[],
31.     dora_indicators=["4z"],
32.     round_wind="1z",
33.     seat_wind="1z",
34.     version="0.9.1",
35. )
36. result = request_recommendation(payload)
37. top3 = rank_stats(result, turn=1, limit=3)
38. ```
39.
40. `top3` 可直接给 HUD：
41. - `tile_str`: 推荐切牌
42. - `shanten`: 切后向听
43. - `necessary_total`: 有效牌总数
44. - `exp_score`: 指定巡期待值
45. - `win_prob`: 指定巡和了率
46. - `tenpai_prob`: 指定巡听牌率
47.
48. 吃碰杠建议不要直接问算法“要不要鸣”。
49. 正确做法是：Crawler 先枚举 `不鸣 / 吃法A / 吃法B / 碰 / 杠` 分支，再分别请求算法比较结果。
