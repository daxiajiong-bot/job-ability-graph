import { Component } from "react";
import { Result, Button } from "antd";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            minHeight: "60vh",
          }}
        >
          <Result
            status="error"
            title="页面出现异常"
            subTitle={this.state.error?.message || "未知错误，请尝试刷新页面"}
            extra={[
              <Button key="retry" type="primary" onClick={this.handleReset}>
                重试
              </Button>,
              <Button key="home" onClick={() => (window.location.href = "/")}>
                返回首页
              </Button>,
            ]}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
