function [range, azimuth, elevation] = xyz2rae(xyz, y, z)
% xyz2rae - Transforms cartesian coordinates (XYZ = East,North,Up) to radar coords R,Az,El
%   input  format #1: [...] = xyz2rae(x, y, z)
%   input  format #2: [...] = xyz2rae(xyz)
%   output format #1: [range, azimuth, elevation] = xyz2rae(...)
%   output format #2: rae = xyz2rae(...)
%
%   Inputs:
%     Format #1:
%       x - see definition in help for cart2sph; positive x = East
%       y - see definition in help for cart2sph; positive y = North
%       z - see definition in help for cart2sph; positive z = Up
%
%     Format #2:
%       xyz - same as format #1, with all 3 values/vector bunched together in a vector/matrix
%
%   Outputs:
%     Format #1:
%       range     - sqrt(x^2 + y^2 + z^2)
%       azimuth   - radian angle clockwize from north (= positive y axis)
%       elevation - radian angle from xy plane to positive z axis
%
%     Format #2:
%       rae - same as format #1, with all 3 values/vector bunched together in a vector/matrix
%
%   Example:
%     [range,az,el] = xyz2rae(1,1,1) => range=1.732, az=-0.785, el=0.615
%     rae = xyz2rae([1,1,1])         => rae = [1.732, -0.785, 0.615]
%
%   Notes:
%     Note the different definitions of azimuth here vs. Malab's cart2sph.
%     Also note the different format of input and output args: The input
%     coordinates here may be either singular values or a vector of
%     coordinate points.
%
%     Use the corresponding rae2xyz function for the reverse transformation.
%
%     xyz2rae does NOT take into account earth curvature, Ionosphere beam
%     curving etc. - this simple function uses a simple flat-earth free-space
%     model.
%
%   See also: rae2xyz, cart2sph, cart2pol
% Programmed by Yair M. Altman: altmany(at)gmail.com
% $Revision: 1.4 $  $Date: 2007/08/24 10:00:39 $
  %try
      % Process input args
      transposed = 0;
      if nargin < 2
          if isempty(xyz),  range = [];  azimuth = [];  elevation = [];  return;  end
          % ensure that coord points are column-wise
          if size(xyz,2) == 1
              xyz = xyz';
              transposed = 1;
          end
          % ensure that we have enough coord data
          if size(xyz,2) == 1
              error('input must be a vactor or matrix with at least 2 coordinate values');
          elseif size(xyz,2) == 2
              xyz(:,3) = 0;
          elseif size(xyz,2) > 3
              warning('input must be a 2- or 3-dimensional vector/matrix - extra data is ignored');  %#ok for ML6
          end
          x = xyz(:,1);
          y = xyz(:,2);
          z = xyz(:,3);
      else
          x = xyz;
          if nargin == 2
              % handle 2-D data (z=0)
              z = zeros(size(x));
          end
      end
      % Convert using Matlab's generic cart2sph
      [a,e,r] = cart2sph(x,y,z);
      % Transform the azimuth and send to output args
      if nargout > 1
          % format #1:
          range = r;
          azimuth = pi/2 - a;      % use -a instead of pi/2-a if azimuth 0 is Eastward, not Northward
          if nargout > 2,  elevation = e;  end
      else%if nargout
          % format #2:
          if all(size(r) > 1)
              range = {r, pi/2-a, e};  % use -a instead of pi/2-a if azimuth 0 is Eastward, not Northward
          elseif size(r,2) > size(r,1)
              range = [r; pi/2-a; e];  % use -a instead of pi/2-a if azimuth 0 is Eastward, not Northward
          else
              range = [r, pi/2-a, e];  % use -a instead of pi/2-a if azimuth 0 is Eastward, not Northward
          end
      end
      % Transpose result if inputs were transposed
      if transposed
          range = range';
          if exist('azimuth','var'),  azimuth = azimuth';  end
          if exist('elevation','var'),  elevation = elevation';  end
      end
  %catch
  %    handleError;
  %end
