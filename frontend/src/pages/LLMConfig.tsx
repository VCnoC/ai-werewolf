import { useEffect, useState } from "react";
import {
  Typography,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Space,
  App,
  Popconfirm,
  Tag,
  Switch,
} from "antd";
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ApiOutlined,
} from "@ant-design/icons";
import { api, type LLMConfigDTO, type LLMConfigCreate } from "../services/api";

export default function LLMConfig() {
  const { message } = App.useApp();
  const [configs, setConfigs] = useState<LLMConfigDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm<LLMConfigCreate>();

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const data = await api.getLLMConfigs();
      setConfigs(data);
    } catch (e) {
      message.error(`加载配置失败: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigs();
  }, []);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    try {
      if (editingId) {
        // 编辑模式：空 api_key 表示不修改，从提交数据中移除
        const { api_key, ...rest } = values;
        const updateData: Partial<LLMConfigCreate> = { ...rest };
        if (api_key) {
          updateData.api_key = api_key;
        }
        await api.updateLLMConfig(editingId, updateData);
        message.success("更新成功");
      } else {
        await api.createLLMConfig(values);
        message.success("创建成功");
      }
      setModalOpen(false);
      form.resetFields();
      setEditingId(null);
      fetchConfigs();
    } catch (e) {
      message.error(`操作失败: ${e instanceof Error ? e.message : e}`);
    }
  };

  const handleEdit = (record: LLMConfigDTO) => {
    setEditingId(record.id);
    form.setFieldsValue({
      name: record.name,
      api_url: record.api_url,
      api_key: "",
      model_name: record.model_name,
      append_chat_path: record.append_chat_path,
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await api.deleteLLMConfig(id);
      message.success("删除成功");
      fetchConfigs();
    } catch (e) {
      message.error(`删除失败: ${e instanceof Error ? e.message : e}`);
    }
  };

  const handleTest = async (id: number) => {
    try {
      const result = await api.testLLMConfig(id);
      if (result.success) {
        message.success(result.message);
      } else {
        message.warning(result.message);
      }
    } catch (e) {
      message.error(`测试失败: ${e instanceof Error ? e.message : e}`);
    }
  };

  const columns = [
    { title: "名称", dataIndex: "name", key: "name" },
    { title: "API 地址", dataIndex: "api_url", key: "api_url", ellipsis: true },
    {
      title: "API Key",
      dataIndex: "api_key_masked",
      key: "api_key_masked",
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: "模型", dataIndex: "model_name", key: "model_name" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, record: LLMConfigDTO) => (
        <Space>
          <Button
            size="small"
            icon={<ApiOutlined />}
            onClick={() => handleTest(record.id)}
          >
            测试
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          LLM 配置管理
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditingId(null);
            form.resetFields();
            setModalOpen(true);
          }}
        >
          新增配置
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={configs}
        rowKey="id"
        loading={loading}
        pagination={false}
      />

      <Modal
        title={editingId ? "编辑配置" : "新增配置"}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => {
          setModalOpen(false);
          form.resetFields();
          setEditingId(null);
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input placeholder="例如：DeepSeek-V3" />
          </Form.Item>
          <Form.Item name="api_url" label="API 地址" rules={[{ required: true }]}>
            <Input placeholder="例如：https://api.deepseek.com/v1" />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            rules={[{ required: !editingId }]}
          >
            <Input.Password placeholder={editingId ? "留空则不修改" : "输入 API Key"} />
          </Form.Item>
          <Form.Item name="model_name" label="模型名称" rules={[{ required: true }]}>
            <Input placeholder="例如：deepseek-chat" />
          </Form.Item>
          <Form.Item
            name="append_chat_path"
            label="自动拼接 /chat/completions"
            valuePropName="checked"
            initialValue={true}
            tooltip="开启后会在 API 地址后自动拼接 /chat/completions，关闭则直接请求填写的地址"
          >
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
