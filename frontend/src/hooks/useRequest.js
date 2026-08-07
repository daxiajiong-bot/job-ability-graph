import { useState, useCallback, useRef, useEffect } from "react";
import { message } from "antd";

/**
 * 统一请求状态管理 hook
 * @param {Function} requestFn - 请求函数（返回 Promise）
 * @param {Object} options - 配置项
 * @param {boolean} options.manual - 是否手动触发（默认 false 自动执行）
 * @param {number} options.timeout - 超时时间 ms（默认 10000）
 * @param {number} options.retries - 重试次数（默认 2）
 * @param {Function} options.onSuccess - 成功回调
 * @param {Function} options.onError - 失败回调
 * @param {string} options.errorMessage - 自定义错误提示
 */
export default function useRequest(requestFn, options = {}) {
  const {
    manual = false,
    timeout = 10000,
    retries = 2,
    onSuccess,
    onError,
    errorMessage,
  } = options;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  const run = useCallback(
    async (...args) => {
      // 取消上一次未完成的请求
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      if (mountedRef.current) {
        setLoading(true);
        setError(null);
      }

      let lastError = null;
      for (let attempt = 0; attempt <= retries; attempt++) {
        try {
          // 超时控制
          const timeoutId = setTimeout(() => {
            if (attempt === retries) {
              controller.abort();
            }
          }, timeout);

          const result = await requestFn(...args);
          clearTimeout(timeoutId);

          if (!controller.signal.aborted && mountedRef.current) {
            setData(result);
            setLoading(false);
            onSuccess?.(result);
          }
          return result;
        } catch (e) {
          lastError = e;
          if (controller.signal.aborted) break;
          // 非最后一次重试时等待一段时间再重试
          if (attempt < retries) {
            await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)));
          }
        }
      }

      if (mountedRef.current) {
        setError(lastError);
        setLoading(false);
        const msg =
          errorMessage ||
          lastError?.response?.data?.error?.message ||
          lastError?.message ||
          "请求失败";
        message.error(msg);
        onError?.(lastError);
      }
      return null;
    },
    [requestFn, timeout, retries, onSuccess, onError, errorMessage]
  );

  const cancel = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    if (mountedRef.current) setLoading(false);
  }, []);

  return { data, loading, error, run, cancel, setData };
}
