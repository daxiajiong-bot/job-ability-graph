import {
  Card,
  Typography,
  Form,
  Switch,
  Select,
  ColorPicker,
  Button,
  Divider,
  message,
  Space,
  Descriptions,
} from "antd";
import { SettingOutlined, SaveOutlined, UndoOutlined } from "@ant-design/icons";
import useStore from "../store/useStore";

const { Title, Paragraph } = Typography;

const COLOR_PRESETS = [
  { label: "冰蓝", value: "#4dd6ff" },
  { label: "翠绿", value: "#52c41a" },
  { label: "琥珀", value: "#faad14" },
  { label: "珊瑚", value: "#ff7875" },
  { label: "紫罗兰", value: "#b37feb" },
];

export default function Settings() {
  const { settings, updateSettings } = useStore();
  const [form] = Form.useForm();

  function handleSave(values) {
    updateSettings(values);
    message.success("设置已保存");
  }

  function handleReset() {
    const defaults = {
      theme: "dark",
      primaryColor: "#4dd6ff",
      sidebarCollapsed: false,
      radarColors: ["#4dd6ff", "#52c41a", "#faad14", "#ff4d4f"],
    };
    updateSettings(defaults);
    form.setFieldsValue(defaults);
    message.info("已恢复默认设置");
  }

  return (
    <div>
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <SettingOutlined style={{ marginRight: 8, color: "var(--text-secondary)" }} />
          系统设置
        </Title>
        <Paragraph style={{ color: "var(--text-secondary)", margin: 0 }}>
          自定义界面主题、图表配色和系统偏好
        </Paragraph>
      </div>

      <Form
        form={form}
        layout="vertical"
        initialValues={settings}
        onFinish={handleSave}
        style={{ maxWidth: 600 }}
      >
        <Card title="界面设置">
          <Form.Item label="主题模式" name="theme">
            <Select
              options={[
                { label: "深色模式", value: "dark" },
                { label: "浅色模式", value: "light" },
              ]}
            />
          </Form.Item>

          <Form.Item label="主色调" name="primaryColor">
            <Select
              options={COLOR_PRESETS.map((c) => ({
                label: (
                  <Space>
                    <div
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: 4,
                        background: c.value,
                      }}
                    />
                    {c.label}
                  </Space>
                ),
                value: c.value,
              }))}
            />
          </Form.Item>

          <Form.Item
            label="侧边栏默认收起"
            name="sidebarCollapsed"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Card>

        <Card title="图表设置" style={{ marginTop: 16 }}>
          <Form.Item label="雷达图配色方案">
            <Paragraph type="secondary" style={{ marginBottom: 12 }}>
              当前配色：
              {settings.radarColors?.map((c, i) => (
                <span
                  key={i}
                  style={{
                    display: "inline-block",
                    width: 20,
                    height: 12,
                    background: c,
                    borderRadius: 2,
                    marginLeft: 4,
                    verticalAlign: "middle",
                  }}
                />
              ))}
            </Paragraph>
          </Form.Item>
        </Card>

        <Card title="存储信息" style={{ marginTop: 16 }}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="设置存储">
              localStorage（浏览器本地）
            </Descriptions.Item>
            <Descriptions.Item label="历史记录上限">100 条</Descriptions.Item>
            <Descriptions.Item label="数据清除">
              清除浏览器缓存将重置所有设置
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <div style={{ marginTop: 24 }}>
          <Space>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>
              保存设置
            </Button>
            <Button icon={<UndoOutlined />} onClick={handleReset}>
              恢复默认
            </Button>
          </Space>
        </div>
      </Form>
    </div>
  );
}
