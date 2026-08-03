/**
 * 지정한 시간(ms) 동안 대기합니다.
 */
export function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * getter가 undefined가 아닌 값을 반환할 때까지 대기합니다.
 *
 * @param getter 반환값을 확인할 함수
 * @param timeout 최대 대기 시간(ms)
 * @param interval 검사 주기(ms)
 * @returns getter가 반환한 값 또는 timeout 시 undefined
 */
export async function waitUntil<T>(
    getter: () => T | undefined,
    timeout: number = 5000,
    interval: number = 100
): Promise<T | undefined> {

    const start = Date.now();

    while (Date.now() - start < timeout) {

        const value = getter();

        if (value !== undefined) {
            return value;
        }

        await sleep(interval);
    }

    return undefined;
}