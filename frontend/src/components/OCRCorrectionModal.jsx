import { useState, useEffect } from "react";
import { Modal, Input, Typography, Tag, Space, Button, message } from "antd";
import { EditOutlined, CheckOutlined, ReloadOutlined } from "@ant-design/icons";

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

/**
 * OCR 识别结果校正弹窗
 * @param {Object} props
 * @param {boolean} props.open - 是否打开
 * @param {Function} props.onClose - 关闭回调
 * @param {Function} props.onConfirm - 确认回调 (修正后的文本)
 * @param {string} props.ocrText - OCR 识别的原始文本
 * @param {string} props.confidence - 置信度信息
 * @param {string} props.filename - 文件名
 * @param {string} props.documentType - 文档类型 (jd/resume)
 */
export default function OCRCorrectionModal({
  open,
  onClose,
  onConfirm,
  ocrText = "",
  confidence,
  filename,
  documentType = "jd",
}) {
  const [editedText, setEditedText] = useState(ocrText);
  const [isEditing, setIsEditing] = useState(false);

  useEffect(() => {
    setEditedText(ocrText);
    setIsEditing(false);
  }, [ocrText, open]);

  function handleConfirm() {
    if (!editedText.trim()) {
      message.warning("文本内容不能为空");
      return;
    }
    onConfirm(editedText);
    onClose();
  }

  function handleReset() {
    setEditedText(ocrText);
    message.info("已恢复原始识别文本");
  }

  return (
    <Modal
      title={
        <Space>
          <EditOutlined />
          <span>OCR 识别结果校正</span>
          {filename && <Tag>{filename}</Tag>}
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={720}
      footer={[
        <Button key="reset" icon={<ReloadOutlined />} onClick={handleReset}>
          恢复原文
        </Button>,
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="confirm"
          type="primary"
          icon={<CheckOutlined />}
          onClick={handleConfirm}
        >
          确认使用
        </Button>,
      ]}
    >
      <div style={{ marginBottom: 12 }}>
        <Space>
          {confidence && (
            <Tag color={Number(confidence) > 80 ? "green" : Number(confidence) > 60 ? "orange" : "red"}>
              置信度：{confidence}%
            </Tag>
          )}
          <Tag color="blue">
            {documentType === "jd" ? "岗位描述" : "候选人简历"}
          </Tag>
          <Text type="secondary">
            请检查 OCR 识别结果，修正错误后点击「确认使用」
          </Text>
        </Space>
      </div>

      <TextArea
        value={editedText}
        onChange={(e) => setEditedText(e.target.value)}
        rows={16}
        style={{ fontSize: 13, lineHeight: 1.8 }}
        placeholder="OCR 识别结果将在此显示..."
      />

      {editedText !== ocrText && (
        <Paragraph
          type="warning"
          style={{ marginTop: 8, fontSize: 12 }}
        >
          ⚠ 文本已被修改
        </Paragraph>
      )}
    </Modal>
  );
}
