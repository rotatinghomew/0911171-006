# 支持需求与排班回测

容器环境固定在仓库 Dockerfile 的 Python 3.11.14 镜像摘要，数值分析依赖与传递依赖在 requirements.txt 中精确锁定。执行 `docker build -t local-analytics .` 后，`docker run --rm --network none local-analytics` 运行内置例子；`docker run --rm --network none local-analytics python -m unittest discover -s tests -v` 运行测试。构建时安装依赖，运行时无需联网；非容器环境使用 Python 3.11，并先执行 `python -m pip install -r requirements.txt`。

此服务用合成工单预测渠道需求，并在技能和班次约束下估算排班覆盖。

运行 `python -m unittest discover -s tests -v`；运行 `python -m support.demo` 查看一组情景。回测结果是容量规划参考，不是服务水平保证。

`support.roster.Roster` 保存员工渠道技能、时薪与已排班次，同一员工不能在重叠时段重复排班。班次终点不含在覆盖中，小时编号可以跨过 24，容量摘要再映射到一天中的时段。`assess` 将排班覆盖和工单小时分布相比较；目前每人每小时按一个容量单位计，不模拟排队、处理时长或技能共享调度，不能把未覆盖工单数解释为真实等待人数。
