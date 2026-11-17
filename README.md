# 支持需求与排班回测

容器环境固定在仓库 Dockerfile 的 Python 3.11.14 镜像摘要，数值分析依赖与传递依赖在 requirements.txt 中精确锁定。执行 `docker build -t local-analytics .` 后，`docker run --rm --network none local-analytics` 运行内置例子；`docker run --rm --network none local-analytics python -m unittest discover -s tests -v` 运行测试。构建时安装依赖，运行时无需联网；非容器环境使用 Python 3.11，并先执行 `python -m pip install -r requirements.txt`。

此服务用合成工单预测渠道需求，把需求分析与 `Roster` 连成排班情景回测：在同一需求情景下重演多份班表，比较等待、放弃、跨班积压与人员成本。回测结果是容量规划参考，不是服务水平保证，也不会向真实团队自动下发排班。

运行 `python -m unittest discover -s tests -v`；运行 `python -m support.demo` 查看一段含夜班衔接与技能瓶颈的节假日业务日重放。

## 工单与预测（support.forecast）

工单字段：`channel`、`created_hour`（绝对小时，可跨天，如 25.5 表示次日 1:30）、`language`、`handle_hours`、`known_at_hour`（记录对排班可见的时刻，缺省等于 `created_hour`）。

`forecast_demand(tickets, as_of_hour, ...)` 只使用 `known_at_hour <= as_of_hour` 的工单：事后补录的工单（`known_at_hour` 晚于创建时刻）不会进入决策时点之前的预测，历史回测因此不会在补录后悄悄变成"用未来信息做出的预测"。预测快照带 `decision_hour`，生成后不再随数据变化。节假日上浮（`holiday_uplift`）、渠道迁移（`migration`，按份额把源渠道需求搬到目标渠道）与来量波动（`volume_factor`）作为显式参数保留在预测里；`forecast_error` 把预测快照与实际工单按渠道对照（总量偏差与逐小时 MAE）。

## 排班（support.roster）

`Roster` 保存员工渠道技能（`channels`）、语言技能（`languages`，缺省视为通配）、时薪与已排班次，同一员工不能在重叠时段重复排班。班次终点不含在覆盖中，小时编号可以跨过 24（如夜班 22:00–06:00 记为 22–30），容量摘要再映射到一天中的时段。`assess` 仍提供旧的每小时人头对照；它只是静态参考，不模拟排队、处理时长或技能共享调度，不能把未覆盖工单数解释为真实等待人数。

## 服务重演（support.simulation）

`simulate(tickets, bookings, agents, patience, horizon_end)` 按工单到达、处理时长、语言技能与班次边界做离散事件重演：

- 同一员工同一时刻至多服务一张工单——多技能员工不会被两个渠道各算一次（`assert_single_server` 校验服务区间不重叠）。
- 各渠道有独立耐心（`patience`，小时）：语音不能久等，超时放弃；异步消息可以等，`None` 表示不放弃、留作积压。
- 员工交班时仍在处理的工单会处理完再走（计加班；首尾相接的班次衔接不算加班），但不会接新工单。
- 在每个班次终点与重演截止时刻记录跨班积压快照；截止时仍在排队的工单记为 backlog。

等待分位数只统计已服务工单；长期无人处理的工单体现在积压与放弃里，因此约束要同时覆盖等待、放弃与积压三类信号。

## 可解释约束与情景对比（support.constraints / support.backtest）

约束逐条给出是否满足与依据（观测值、阈值、样本量）：`MaxWait`（渠道等待分位数上限）、`MaxAbandonRate`（放弃率上限）、`MaxBacklog`（指定班次边界或截止时刻的积压上限）、`MaxOvertime`（加班总小时上限）。`run_scenario` 在同一批工单下重演一份班表并核对约束；`compare_rosters` 对比多份班表，给出最便宜班表、可行班表与最便宜可行班表——低预测误差不代表排班合理，是否可用以约束证据为准。

## 内置例子（support.demo）

节假日业务日（08:00 至次日 08:00，夜班 00:00–08:00 跨午夜）：先用前 14 天已知工单在决策时点做预测，再重放两个需求情景（与预测一致 / 含未知来量波动）下 baseline 与 cheap 两份班表。可以看到需求误差怎样传到等待、放弃与跨班积压，以及更便宜的班表（砍晚班日语坐席、夜班无日语技能、夜间不清理异步积压）为什么未必可用。
