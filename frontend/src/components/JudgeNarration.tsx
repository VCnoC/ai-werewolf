import { Typography } from "antd";
import { SoundOutlined } from "@ant-design/icons";

interface Props {
  text: string;
}

export default function JudgeNarration({ text }: Props) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "8px 16px",
        margin: "12px 0",
        background: "linear-gradient(135deg, #fffbe6 0%, #fff7e6 100%)",
        border: "1px solid #ffe58f",
        borderRadius: 8,
      }}
    >
      <Typography.Text
        style={{ color: "#d48806", fontWeight: 500, fontSize: 14 }}
      >
        <SoundOutlined style={{ marginRight: 8 }} />
        {text}
      </Typography.Text>
    </div>
  );
}
