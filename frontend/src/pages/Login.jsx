import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Radio, message, Tabs } from 'antd'
import { UserOutlined, LockOutlined, TeamOutlined, IdcardOutlined } from '@ant-design/icons'
import useStore from '../store/useStore'
import { authAPI } from '../api/client'

export default function Login() {
  const [activeTab, setActiveTab] = useState('login')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { login } = useStore()

  const handleLogin = async (values) => {
    setLoading(true)
    try {
      const res = await authAPI.login(values)
      const { token, user } = res.data.data
      login(token, user)
      message.success(`欢迎回来，${user.display_name || user.username}！`)
      navigate('/', { replace: true })
    } catch (err) {
      message.error(err.response?.data?.error?.message || '登录失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (values) => {
    if (values.password !== values.confirmPassword) {
      message.error('两次输入的密码不一致')
      return
    }
    setLoading(true)
    try {
      const { confirmPassword, ...data } = values
      const res = await authAPI.register(data)
      const { token, user } = res.data.data
      login(token, user)
      message.success(`注册成功，欢迎 ${user.display_name || user.username}！`)
      navigate('/', { replace: true })
    } catch (err) {
      message.error(err.response?.data?.error?.message || '注册失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const tabItems = [
    {
      key: 'login',
      label: '登录',
      children: (
        <Form onFinish={handleLogin} size="large" autoComplete="off">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'register',
      label: '注册',
      children: (
        <Form onFinish={handleRegister} size="large" autoComplete="off">
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少3个字符' },
              { pattern: /^[a-zA-Z0-9_一-鿿]+$/, message: '只能包含字母、数字、下划线和中文' },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item
            name="display_name"
            rules={[{ max: 64, message: '显示名称最多64个字符' }]}
          >
            <Input prefix={<IdcardOutlined />} placeholder="显示名称（选填）" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少6个字符' },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item
            name="confirmPassword"
            rules={[{ required: true, message: '请确认密码' }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>
          <Form.Item
            name="role"
            initialValue="job_seeker"
            rules={[{ required: true, message: '请选择角色' }]}
          >
            <Radio.Group buttonStyle="solid">
              <Radio.Button value="job_seeker">
                <TeamOutlined /> 求职者
              </Radio.Button>
              <Radio.Button value="hr">
                <UserOutlined /> HR
              </Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              注册
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ]

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo">
            <span className="logo-icon">🌟</span>
            <h1>岗位能力图谱</h1>
          </div>
          <p className="login-subtitle">新一代信息技术岗位全景图谱 · 智能人岗匹配系统</p>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          items={tabItems}
          className="login-tabs"
        />
      </div>
    </div>
  )
}
