import { NextRequest, NextResponse } from 'next/server';

export interface DevRouteEnvironment {
  readonly NODE_ENV?: string;
  readonly OBSERVATORY_DATA_SOURCE?: string;
}

/** Shared, fail-closed ingress rule for every /dev route. */
export function createDevRouteMiddleware(env: DevRouteEnvironment) {
  return (request: NextRequest): NextResponse | null => {
    const pathname = request.nextUrl.pathname;
    if (env.NODE_ENV === 'production' && (pathname === '/dev' || pathname.startsWith('/dev/'))) {
      return new NextResponse(null, { status: 404 });
    }
    return null;
  };
}

export function middleware(request: NextRequest): NextResponse {
  const response = createDevRouteMiddleware(process.env)(request);
  return response ?? NextResponse.next();
}

export const config = {
  matcher: ['/dev/:path*'],
};
