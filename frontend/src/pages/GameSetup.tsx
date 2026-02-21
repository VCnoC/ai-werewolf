import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Typography,
  Card,
  Select,
  Button,
  Row,
  Col,
  App,
  Dropdown,
  Space,
  Spin,
} from "antd";
import { DownOutlined, PlayCircleOutlined, UserOutlined } from "@ant-design/icons";
import { api, type LLMConfigDTO } from "../services/api";

export default function GameSetup() {
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [configs, setConfigs] = useState<LLMConfigDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selections, setSelections] = useState<(number | null)[]>(
    Array(12).fill(null)
  );

  useEffect(() => {
    setLoading(true);
    api
      .getLLMConfigs()
      .then(setConfigs)
      .catch((e) => message.error(`加载配置失败: ${e instanceof Error ? e.message : e}`))
      .finally(() => setLoading(false));
  }, []);

  const handleSelectAll = (configId: number) => {
    setSelections(Array(12).fill(configId));
  };

  const handleCreate = async () => {
    if (selections.some((s) => s === null)) {
      message.warning("请为所有12个AI选择LLM配置");
      return;
    }
    setCreating(true);
    try {
      const result = await api.createGame({
        player_configs: selections as number[],
      });
      message.success("游戏创建成功！");
      // 开始游戏
      await api.startGame(result.game_id);
      navigate(`/game/${result.game_id}`);
    } catch (e) {
      message.error(`创建失败: ${e instanceof Error ? e.message : e}`);
    } finally {
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <Typography.Title level={2}>游戏开局设置</Typography.Title>
      <Typography.Paragraph type="secondary">
        为12个AI玩家选择LLM配置，角色将在游戏开始时随机分配
      </Typography.Paragraph>

      {configs.length > 0 && (
        <Space style={{ marginBottom: 16 }}>
          <Typography.Text>快速填充：</Typography.Text>
          <Dropdown
            menu={{
              items: configs.map((c) => ({
                key: String(c.id),
                label: `全部使用 ${c.name} (${c.model_name})`,
              })),
              onClick: ({ key }) => handleSelectAll(Number(key)),
            }}
          >
            <Button size="small">
              选择配置 <DownOutlined />
            </Button>
          </Dropdown>
        </Space>
      )}

      <Row gutter={[16, 16]}>
        {Array.from({ length: 12 }, (_, i) => (
          <Col key={i} xs={24} sm={12} md={8} lg={6}>
            <Card
              size="small"
              title={
                <Space>
                  <UserOutlined />
                  <span>{i + 1}号玩家</span>
                </Space>
              }
            >
              <Select
                style={{ width: "100%" }}
                placeholder="选择LLM配置"
                value={selections[i]}
                onChange={(v) => {
                  const next = [...selections];
                  next[i] = v;
                  setSelections(next);
                }}
                options={configs.map((c) => ({
                  label: `${c.name} (${c.model_name})`,
                  value: c.id,
                }))}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <div style={{ marginTop: 24, textAlign: "center" }}>
        <Button
          type="primary"
          size="large"
          icon={<PlayCircleOutlined />}
          onClick={handleCreate}
          loading={creating}
          disabled={selections.some((s) => s === null)}
        >
          开始游戏
        </Button>
      </div>
    </div>
  );
}
