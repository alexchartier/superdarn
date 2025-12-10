function [Pgc,Pgroup,Pphase] = raytrace_croft_orig(f0,beta0,fm,hm,ym)
        
    F = f0./fm;
    
    r0 = 6371;
    rm = r0 + hm;
    rb = rm - ym;
    
    gamma = acos(r0.*cos(beta0)./rb);
    
    A = 1 - 1./(F.^2) + (rb./(F.*ym)).^2;
    B = - 2*rm.*rb.^2./(F.^2.*ym.^2);
    C = ((rb.*rm)./(F.*ym)).^2-(r0.*cos(beta0)).^2;
    
    Pgc = 2*r0*((gamma - beta0) - (r0.*cos(beta0)./(2*sqrt(C))).*...
        log((B.^2-4*A.*C)./(4*C.*(sin(gamma) + (1./rb).*sqrt(C)+...
        B./(2*sqrt(C))).^2)));
    
    Pgroup = 2*(rb.*sin(gamma) - r0.*sin(beta0) + (1./A).*...
        (-rb.*sin(gamma) - (B./(4.*sqrt(A))).*log((B.^2 - 4.*A.*C)./...
        (2*A.*rb + B +2*rb.*sqrt(A).*sin(gamma)).^2)));
    
    Pphase = 2*(-r0.*sin(beta0) + (B/4).*((1./sqrt(A)).*...
        log((B.^2-4*A.*C)./(4*(A.*rb+(B/2)+sqrt(A).*rb.*sin(gamma)).^2)) + ...
        (rm./sqrt(C)).*log((B.^2-4*A.*C)./(4*C.*(sin(gamma)+...
        sqrt(C)./rb + B./(2*sqrt(C))).^2))));
    
  
