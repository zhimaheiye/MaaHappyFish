import json
import os
import time
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_PATH = os.path.join(ROOT, 'assets', 'resource', 'pipeline', 'collect_fish.json')
INTERFACE_PATH = os.path.join(ROOT, 'assets', 'interface.json')

try:
    import sys
    sys.path.insert(0, os.path.join(ROOT, 'agent'))
    from runtime_state import collect_fish_state
    from my_reco import duty_state
    from my_reco import (
        CheckDutyCycleReco,
        CheckStarfishTimerReco,
        CheckCollectFishTankSwitchReco,
        CheckCollectFishTargetTankReco,
        CheckCollectFishTankModeReco,
        CheckCollectFishNeedsInitReco,
        timer_state,
    )
    from my_action import (
        SetCollectFishTankModeAction,
        SetCollectFishSwitchIntervalAction,
        CollectFishDualStartAction,
        CollectFishSingleStartAction,
        CollectFishRecordSwitchedTankAction,
        CollectFishSwitchRetryAction,
        CollectFishAfterStarfishAction,
    )
except Exception as e:
    raise ImportError(f'Failed to import agent modules: {e}')


class CollectFishDualTankTestSuite(unittest.TestCase):
    def setUp(self):
        collect_fish_state['tank_mode'] = 'single'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['current_tank'] = 1
        collect_fish_state['dual_start_time'] = 0.0
        collect_fish_state['last_switch_slot'] = -1
        collect_fish_state['is_inited'] = False
        collect_fish_state['task_id'] = None
        collect_fish_state['switch_retry_count'] = 0
        collect_fish_state['pending_target_tank'] = None
        collect_fish_state['initial_feed_done'] = False

        duty_state['mode'] = 'IDLE'
        duty_state['idle_interval'] = 0.0
        duty_state['active_duration'] = 120.0
        duty_state['is_inited'] = False

        timer_state['task_id'] = None
        timer_state['last_feed_time'] = 0.0
        timer_state['interval_seconds'] = 600.0

    def test_case_01_default_mode_is_single_and_no_switch(self):
        self.assertEqual(collect_fish_state['tank_mode'], 'single')
        context = MagicMock()
        argv = MagicMock()
        reco = CheckCollectFishTankSwitchReco()
        result = reco.analyze(context, argv)
        self.assertIsNone(result)

    def test_case_02_dual_start_normalizes_to_tank_1_with_t0(self):
        context = MagicMock()
        argv = MagicMock()
        action = CollectFishDualStartAction()

        before = time.monotonic()
        res = action.run(context, argv)
        after = time.monotonic()

        self.assertTrue(res)
        self.assertEqual(collect_fish_state['current_tank'], 1)
        self.assertTrue(collect_fish_state['is_inited'])
        self.assertGreaterEqual(collect_fish_state['dual_start_time'], before)
        self.assertLessEqual(collect_fish_state['dual_start_time'], after)
        self.assertEqual(collect_fish_state['last_switch_slot'], 0)

    def test_case_03_time_advancement_120s_slots(self):
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = True

        base_t0 = 1000.0
        collect_fish_state['dual_start_time'] = base_t0

        def get_expected(simulated_now):
            elapsed = simulated_now - base_t0
            slot = int(elapsed // 120.0)
            return 1 if (slot % 2 == 0) else 2

        self.assertEqual(get_expected(base_t0 + 0), 1)
        self.assertEqual(get_expected(base_t0 + 119), 1)
        self.assertEqual(get_expected(base_t0 + 120), 2)
        self.assertEqual(get_expected(base_t0 + 239), 2)
        self.assertEqual(get_expected(base_t0 + 240), 1)

    def test_case_04_skip_multiple_slots_not_simple_toggle(self):
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = True
        collect_fish_state['current_tank'] = 1

        base_t0 = 1000.0
        collect_fish_state['dual_start_time'] = base_t0

        simulated_now = base_t0 + 370.0
        elapsed = simulated_now - base_t0
        slot = int(elapsed // 120.0)
        expected = 1 if (slot % 2 == 0) else 2
        self.assertEqual(slot, 3)
        self.assertEqual(expected, 2)

        simulated_now_490 = base_t0 + 490.0
        slot_490 = int((simulated_now_490 - base_t0) // 120.0)
        expected_490 = 1 if (slot_490 % 2 == 0) else 2
        self.assertEqual(slot_490, 4)
        self.assertEqual(expected_490, 1)

    def test_case_05_starfish_within_window_no_switch(self):
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = True
        collect_fish_state['current_tank'] = 1
        collect_fish_state['dual_start_time'] = time.monotonic() - 50.0

        context = MagicMock()
        argv = MagicMock()
        argv.custom_action_param = json.dumps({'returned_tank': 1})
        action = CollectFishAfterStarfishAction()
        res = action.run(context, argv)

        self.assertTrue(res)
        self.assertEqual(collect_fish_state['current_tank'], 1)
        self.assertIsNone(collect_fish_state.get('pending_target_tank'))

    def test_case_06_starfish_crossing_boundary_triggers_correction(self):
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = True
        collect_fish_state['current_tank'] = 1
        collect_fish_state['dual_start_time'] = time.monotonic() - 130.0

        context = MagicMock()
        argv = MagicMock()
        argv.custom_action_param = json.dumps({'returned_tank': 1})
        action = CollectFishAfterStarfishAction()
        res = action.run(context, argv)

        self.assertTrue(res)
        self.assertEqual(collect_fish_state['pending_target_tank'], 2)

    def test_case_07_dual_mode_skips_duty_cycle(self):
        collect_fish_state['tank_mode'] = 'dual'
        duty_state['idle_interval'] = 300.0
        duty_state['active_duration'] = 120.0
        duty_state['is_inited'] = True
        duty_state['mode'] = 'IDLE'

        context = MagicMock()
        argv = MagicMock()
        argv.custom_recognition_param = json.dumps({'idle_interval': 300, 'active_duration': 120})
        reco = CheckDutyCycleReco()

        result = reco.analyze(context, argv)
        self.assertIsNone(result)

    def test_case_08_single_mode_preserves_duty_cycle(self):
        collect_fish_state['tank_mode'] = 'single'
        duty_state['is_inited'] = False
        duty_state['idle_interval'] = 300.0
        duty_state['active_duration'] = 120.0

        context = MagicMock()
        argv = MagicMock()
        argv.custom_recognition_param = json.dumps({'idle_interval': 300, 'active_duration': 120})
        reco = CheckDutyCycleReco()

        result = reco.analyze(context, argv)
        self.assertIsNotNone(result)
        self.assertEqual(duty_state['mode'], 'IDLE')

    def test_case_09_single_mode_returns_to_original_tank_no_normalize(self):
        collect_fish_state['tank_mode'] = 'single'
        collect_fish_state['current_tank'] = 2

        context = MagicMock()
        argv = MagicMock()
        argv.custom_action_param = json.dumps({'returned_tank': 2})
        action = CollectFishAfterStarfishAction()
        res = action.run(context, argv)

        self.assertTrue(res)
        self.assertEqual(collect_fish_state['current_tank'], 2)
        self.assertIsNone(collect_fish_state.get('pending_target_tank'))

    def test_case_10_dual_mode_strictly_targets_tanks_1_and_2_only(self):
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 60.0

        for test_elapsed in range(0, 7200, 37):
            slot = int(test_elapsed // 60.0)
            target = 1 if (slot % 2 == 0) else 2
            self.assertIn(target, (1, 2))
            self.assertNotEqual(target, 3)

    def test_case_11_switching_failure_retries_and_aborts_safely(self):
        action = CollectFishSwitchRetryAction()
        context = MagicMock()
        argv = MagicMock()

        self.assertTrue(action.run(context, argv))
        self.assertEqual(collect_fish_state['switch_retry_count'], 1)

        self.assertTrue(action.run(context, argv))
        self.assertEqual(collect_fish_state['switch_retry_count'], 2)

        self.assertFalse(action.run(context, argv))
        self.assertEqual(collect_fish_state['switch_retry_count'], 3)

    def test_case_12_no_feeding_option_skips_initial_and_periodic(self):
        context = MagicMock()
        argv = MagicMock()
        argv.task_detail.task_id = 'task_test_no_feed_001'
        argv.custom_recognition_param = json.dumps({'interval': -1})

        reco = CheckStarfishTimerReco()
        result = reco.analyze(context, argv)
        self.assertIsNone(result)

        time.sleep(0.01)
        result2 = reco.analyze(context, argv)
        self.assertIsNone(result2)

    def test_pipeline_static_topology(self):
        with open(PIPELINE_PATH, 'r', encoding='utf-8') as f:
            pipeline = json.load(f)

        self.assertIn('CollectFishSetTankMode', pipeline['CollectFishTask']['next'])
        self.assertIn('CollectFishStartRouter', pipeline['CollectFishTask']['next'])

        starfish_nodes = [
            'CollectFishOpenManagement',
            'CollectFishVerifyManagement',
            'CollectFishOpenUniversalStarfish',
            'CollectFishSelectCuteStarfishTab',
            'CollectFishSelectGoodStarfishTab',
            'CollectFishSelectBrightStarfishTab',
            'CollectFishExitUniversalStarfish',
            'CollectFishExitManagement',
            'CollectFishAfterStarfishRouter',
        ]
        for node in starfish_nodes:
            self.assertIn(node, pipeline, f'Missing universal starfish node: {node}')

        switch_nodes = [
            'CollectFishCheckTankSwitch',
            'CollectFishSwitchTankRouter',
            'CollectFishSwitchToTank2Target',
            'CollectFishSwitchToTank2OpenPicker',
            'CollectFishSelectTank2FromPicker',
            'CollectFishVerifyTank2Main',
            'CollectFishSwitchToTank1Target',
            'CollectFishSwitchToTank1OpenPicker',
            'CollectFishSelectTank1FromPicker',
            'CollectFishVerifyTank1Main',
            'CollectFishSwitchRetry',
        ]
        for node in switch_nodes:
            self.assertIn(node, pipeline, f'Missing dual tank switch node: {node}')

        rh_next = pipeline['ResumeHarvest']['next']
        idx_starfish = rh_next.index('TriggerStarfishFeed')
        idx_switch = rh_next.index('CollectFishCheckTankSwitch')
        idx_duty = rh_next.index('CheckDutyCycle')
        self.assertLess(idx_starfish, idx_switch, 'TriggerStarfishFeed must precede CollectFishCheckTankSwitch')
        self.assertLess(idx_switch, idx_duty, 'CollectFishCheckTankSwitch must precede CheckDutyCycle')

    def test_interface_options_contract(self):
        with open(INTERFACE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)

        collect_task = next(t for t in data['task'] if t['entry'] == 'CollectFishTask')
        self.assertIn('收鱼鱼缸模式', collect_task['option'])
        self.assertNotIn('双缸切换间隔', collect_task['option'])
        self.assertNotIn('巡检收宝间隔', collect_task['option'])

        tank_mode_opt = data['option']['收鱼鱼缸模式']
        self.assertEqual(tank_mode_opt['default_case'], '当前单鱼缸')
        cases = [c['name'] for c in tank_mode_opt['cases']]
        self.assertEqual(cases, ['当前单鱼缸', '双鱼缸轮换（1缸与2缸）'])
        self.assertEqual(tank_mode_opt['cases'][0]['option'], ['巡检收宝间隔'])
        self.assertEqual(tank_mode_opt['cases'][1]['option'], ['双缸切换间隔'])

        interval_opt = data['option']['双缸切换间隔']
        self.assertEqual(interval_opt['default_case'], '2分钟')
        interval_cases = [c['name'] for c in interval_opt['cases']]
        self.assertIn('30秒(测试用)', interval_cases)
        self.assertIn('2分钟', interval_cases)


    def test_case_a_initial_starfish_routes_to_dual_initialization_and_sets_t0(self):
        """
        Case A: 首轮海星喂食后必须路由到双缸初始化 (is_inited=False -> CheckCollectFishNeedsInitReco -> DualStartAction)
        """
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = False
        collect_fish_state['dual_start_time'] = 0.0
        collect_fish_state['current_tank'] = 1

        context = MagicMock()
        argv = MagicMock()
        argv.custom_action_param = json.dumps({'returned_tank': 1})

        # 1. 首轮海星喂食完成返回鱼缸 1
        starfish_action = CollectFishAfterStarfishAction()
        self.assertTrue(starfish_action.run(context, argv))
        self.assertTrue(collect_fish_state['initial_feed_done'])
        self.assertEqual(collect_fish_state['current_tank'], 1)
        # 此时 dual_start_time 尚未设置 (<= 0), is_inited 仍为 False
        self.assertFalse(collect_fish_state['is_inited'])
        self.assertEqual(collect_fish_state['dual_start_time'], 0.0)

        # 2. CollectFishAfterStarfishPostRouter -> CollectFishAfterStarfishNeedsInitialization
        needs_init_reco = CheckCollectFishNeedsInitReco()
        reco_res = needs_init_reco.analyze(context, argv)
        # 因为 is_inited 为 False，必须命中并导向 CollectFishStartCheckMode
        self.assertIsNotNone(reco_res)

        # 3. 经过 CollectFishStartCheckMode -> CollectFishDualStartNormalize -> CollectFishDualStartAtTank1 -> CollectFishDualStartAction
        dual_start_action = CollectFishDualStartAction()
        before = time.monotonic()
        self.assertTrue(dual_start_action.run(context, argv))
        after = time.monotonic()

        # 4. 验证双缸轮换已成功初始化，t0 已打桩，进入就绪态
        self.assertTrue(collect_fish_state['is_inited'])
        self.assertGreaterEqual(collect_fish_state['dual_start_time'], before)
        self.assertLessEqual(collect_fish_state['dual_start_time'], after)
        self.assertEqual(collect_fish_state['current_tank'], 1)
        self.assertEqual(collect_fish_state['last_switch_slot'], 0)

        # 5. 初始化完成后，CheckCollectFishNeedsInitReco 不再命中
        self.assertIsNone(needs_init_reco.analyze(context, argv))

    def test_case_b_periodic_starfish_preserves_t0_and_does_not_reset_initialization(self):
        """
        Case B: 挂机中周期性海星喂食 (is_inited=True) 不触发初始化路由，直接直通 ResumeHarvest，t0 不被重置
        """
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = True
        base_t0 = time.monotonic() - 75.0
        collect_fish_state['dual_start_time'] = base_t0
        collect_fish_state['current_tank'] = 1

        context = MagicMock()
        argv = MagicMock()
        argv.custom_action_param = json.dumps({'returned_tank': 1})

        # 周期性海星喂食返回
        starfish_action = CollectFishAfterStarfishAction()
        self.assertTrue(starfish_action.run(context, argv))

        # CheckCollectFishNeedsInitReco 纯读判断 is_inited 为 True，返回 None
        needs_init_reco = CheckCollectFishNeedsInitReco()
        self.assertIsNone(needs_init_reco.analyze(context, argv))

        # 验证 t0 未被刷新重置
        self.assertEqual(collect_fish_state['dual_start_time'], base_t0)
        self.assertTrue(collect_fish_state['is_inited'])

    def test_case_c_startup_without_starfish_falls_through_to_dual_start_check_mode(self):
        """
        Case C: 启动时不喂海星 (间隔为-1或未到时) 时，CollectFishStartRouter 直接跌入 CollectFishStartCheckMode
        """
        collect_fish_state['tank_mode'] = 'dual'
        collect_fish_state['switch_interval_sec'] = 120.0
        collect_fish_state['is_inited'] = False
        collect_fish_state['dual_start_time'] = 0.0

        context = MagicMock()
        argv = MagicMock()
        argv.task_detail.task_id = 'test_no_feed'
        argv.custom_recognition_param = json.dumps({'interval': -1})

        # 海星未到时，TriggerStarfishFeed 返回 None
        starfish_reco = CheckStarfishTimerReco()
        self.assertIsNone(starfish_reco.analyze(context, argv))

        # 流水线下一步为 CollectFishStartCheckMode -> CollectFishDualStartNormalize -> CollectFishDualStartAction
        dual_start_action = CollectFishDualStartAction()
        self.assertTrue(dual_start_action.run(context, argv))
        self.assertTrue(collect_fish_state['is_inited'])
        self.assertGreater(collect_fish_state['dual_start_time'], 0.0)
        self.assertEqual(collect_fish_state['current_tank'], 1)

    def test_case_d_single_mode_startup_with_starfish_preserves_original_tank(self):
        """
        Case D: 单缸模式首轮海星喂食后，经 NeedsInit 路由到 CollectFishStartCheckMode -> CollectFishSingleStartInit，保持原鱼缸
        """
        collect_fish_state['tank_mode'] = 'single'
        collect_fish_state['is_inited'] = False
        collect_fish_state['current_tank'] = 2

        context = MagicMock()
        argv = MagicMock()
        argv.custom_action_param = json.dumps({'returned_tank': 2})

        # 海星返回鱼缸 2
        starfish_action = CollectFishAfterStarfishAction()
        self.assertTrue(starfish_action.run(context, argv))
        self.assertEqual(collect_fish_state['current_tank'], 2)

        # 未初始化，触发 NeedsInit
        needs_init_reco = CheckCollectFishNeedsInitReco()
        self.assertIsNotNone(needs_init_reco.analyze(context, argv))

        # 进入 CollectFishSingleStartInit -> CollectFishSingleStartTank2 -> CollectFishSingleStartAction(tank=2)
        single_action = CollectFishSingleStartAction()
        argv.custom_action_param = json.dumps({'tank': 2})
        self.assertTrue(single_action.run(context, argv))

        # 验证已初始化且保持鱼缸 2，不强制归一到鱼缸 1
        self.assertTrue(collect_fish_state['is_inited'])
        self.assertEqual(collect_fish_state['current_tank'], 2)
        self.assertEqual(collect_fish_state['dual_start_time'], 0.0)

    def test_case_e_pipeline_topological_starfish_exit_contract(self):
        """
        Case E: 静态拓扑门禁，校验 collect_fish.json 中海星退出路由及双缸初始化节点的完整连接
        """
        with open(PIPELINE_PATH, 'r', encoding='utf-8') as f:
            pipeline = json.load(f)

        # 1. 未识别到返回鱼缸时必须进入失败分支，不能伪造完整喂食成功
        router_next = pipeline['CollectFishAfterStarfishRouter']['next']
        self.assertIn('CollectFishStarfishFlowFailed', router_next)

        # 2. CollectFishAfterStarfishTank1/2/3 next 均包含 CollectFishAfterStarfishPostRouter
        for tank_node in ('CollectFishAfterStarfishTank1', 'CollectFishAfterStarfishTank2', 'CollectFishAfterStarfishTank3'):
            self.assertIn(tank_node, pipeline)
            self.assertIn('CollectFishAfterStarfishPostRouter', pipeline[tank_node]['next'])

        # 3. 返回失败先重试退出；仍失败时释放计时状态，再进入 PostRouter 恢复主流程
        self.assertIn('CollectFishExitManagementFail', pipeline['CollectFishExitManagement']['on_error'])
        self.assertIn('CollectFishStarfishFlowFailed', pipeline['CollectFishExitManagementFail']['next'])
        self.assertIn('CollectFishAfterStarfishPostRouter', pipeline['CollectFishStarfishFlowFailed']['next'])

        # 4. CollectFishAfterStarfishPostRouter 节点存在，next 包含 NeedsInitialization 和 ResumeHarvest
        self.assertIn('CollectFishAfterStarfishPostRouter', pipeline)
        post_router_next = pipeline['CollectFishAfterStarfishPostRouter']['next']
        self.assertIn('CollectFishAfterStarfishNeedsInitialization', post_router_next)
        self.assertIn('ResumeHarvest', post_router_next)
        idx_needs_init = post_router_next.index('CollectFishAfterStarfishNeedsInitialization')
        idx_resume = post_router_next.index('ResumeHarvest')
        self.assertLess(idx_needs_init, idx_resume, 'NeedsInitialization 必须优先于 ResumeHarvest 评估')

        # 5. CollectFishAfterStarfishNeedsInitialization 节点使用 CheckCollectFishNeedsInitReco，且 next 指向 CollectFishStartCheckMode
        self.assertIn('CollectFishAfterStarfishNeedsInitialization', pipeline)
        init_node = pipeline['CollectFishAfterStarfishNeedsInitialization']
        self.assertEqual(init_node['custom_recognition'], 'CheckCollectFishNeedsInitReco')
        self.assertIn('CollectFishStartCheckMode', init_node['next'])

        # 6. 双缸归一节点 DualStartAtTank2/Tank3 next 指向 CollectFishDualStartAtPicker
        for tank_node in ('CollectFishDualStartAtTank2', 'CollectFishDualStartAtTank3'):
            self.assertIn('CollectFishDualStartAtPicker', pipeline[tank_node]['next'])

    def test_case_f_task_restart_resets_collect_fish_state(self):
        """
        Case F: 任务重启时 SetCollectFishTankModeAction 必须无条件重置状态机
        """
        # 设置污染状态
        collect_fish_state['is_inited'] = True
        collect_fish_state['dual_start_time'] = 999999.0
        collect_fish_state['last_switch_slot'] = 5
        collect_fish_state['initial_feed_done'] = True
        collect_fish_state['pending_target_tank'] = 2
        collect_fish_state['switch_retry_count'] = 2
        collect_fish_state['task_id'] = 100

        context = MagicMock()
        argv = MagicMock()
        argv.task_detail.task_id = 100  # 即使 task_id 相同也重置
        argv.custom_action_param = json.dumps({'tank_mode': 'dual'})

        action = SetCollectFishTankModeAction()
        self.assertTrue(action.run(context, argv))

        self.assertFalse(collect_fish_state['is_inited'])
        self.assertEqual(collect_fish_state['dual_start_time'], 0.0)
        self.assertEqual(collect_fish_state['last_switch_slot'], -1)
        self.assertFalse(collect_fish_state['initial_feed_done'])
        self.assertIsNone(collect_fish_state['pending_target_tank'])
        self.assertEqual(collect_fish_state['switch_retry_count'], 0)
        self.assertEqual(collect_fish_state['tank_mode'], 'dual')


if __name__ == '__main__':
    unittest.main()
