%% notes.m
% SuperDARN experiment notes

% When using Croft's ionosphere as a simulated truth, the optimization is
% capable of retrieving the true ionospheric parameters and therefore can
% estimate the ground path correctly. The problem is highly overdetermined,
% so this procedure should be robust to noise in the observations. The
% ionosphere is only correct in the region where the rays interact with it,
% so extrapolation to other frequency domains is unlikely to be correct.
% In the simulations, this means the slope is usually accurate but the peak
% density and peak height can be inaccurate. The optimizer also seems to be
% sensitive to its boundary conditions - setting these too tightly can
% cause anomalous behavior. 

% The optimization does not retrieve the correct ionosphere when using IRI
% and PHARLAP as a simulated truth. This means the retrieved ionosphere can
% look very odd. The reason may be that Croft's ionosphere/raytracer cannot 
% provide a good match to IRI/PHARLAP - it has to be noted that the Croft 
% ionosphere matching the retrieved ionospheric parameters from IRI does 
% not produce similar group/phase paths to the 'truth' values in the test 
% case. This could be due to either the ionospheric shape or the raytracer
% itself. 

% Things to investigate:
% Should we be using O or X mode from PHARLAP? - many elevation angles have
% two values
% Can we use an IRI basis set with PHARLAP in an alternate algorithm?

% compare_raytracers.m shows the two raytracers do actually produce
% equivalent output 
