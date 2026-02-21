import { Card, Progress, Tag, Typography } from "antd";

interface Props {
  votes: Record<number, number>; // voter -> target
  counts: Record<number, number>; // target -> count
  sheriff: number | null;
}

export default function VotePanel({ votes, counts, sheriff }: Props) {
  const sortedTargets = Object.entries(counts)
    .map(([pid, count]) => ({ pid: Number(pid), count }))
    .sort((a, b) => b.count - a.count);

  const maxCount = sortedTargets.length > 0 ? sortedTargets[0].count : 0;

  return (
    <Card title="🗳️ 投票结果" size="small" style={{ marginBottom: 16 }}>
      {sortedTargets.map(({ pid, count }) => (
        <div
          key={pid}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 8,
          }}
        >
          <Typography.Text style={{ width: 50, flexShrink: 0 }}>
            {pid}号
          </Typography.Text>
          <Progress
            percent={maxCount > 0 ? (count / maxCount) * 100 : 0}
            format={() => `${count}票`}
            strokeColor={count === maxCount ? "#f5222d" : "#1890ff"}
            style={{ flex: 1 }}
            size="small"
          />
        </div>
      ))}

      <div style={{ marginTop: 12, borderTop: "1px solid #f0f0f0", paddingTop: 8 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          投票详情：
        </Typography.Text>
        <div style={{ marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
          {Object.entries(votes).map(([voter, target]) => (
            <Tag key={voter} color={Number(voter) === sheriff ? "gold" : "default"}>
              {voter}号→{target}号
              {Number(voter) === sheriff && " (1.5票)"}
            </Tag>
          ))}
        </div>
      </div>
    </Card>
  );
}
