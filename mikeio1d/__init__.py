import sys
import os
import platform
import pythonnet

from .mikepath import MikePath

# PEP0440 compatible formatted version, see:
# https://www.python.org/dev/peps/pep-0440/
#
# Generic release markers:
#   X.Y
#   X.Y.Z   # For bugfix releases
#
# Admissible pre-release markers:
#   X.YaN   # Alpha release
#   X.YbN   # Beta release
#   X.YrcN  # Release Candidate
#   X.Y     # Final release
#
# Dev branch marker is: 'X.Y.dev' or 'X.Y.devN' where N is an integer.
# 'X.Y.dev0' is the canonical version of 'X.Y.dev'
#
__version__ = "0.4.0"

if "64" not in platform.architecture()[0]:
    raise Exception("This library has not been tested for a 32 bit system.")

MikePath.setup_mike_installation(sys.path)

is_linux = platform.system() == "Linux"
if is_linux:
    import mikecore

    runtime_config = os.path.join(MikePath.mike_bin_path, "DHI.Mike1D.Application.runtimeconfig.json")
    pythonnet.load("coreclr", runtime_config=runtime_config)

import clr

clr.AddReference("System")
clr.AddReference("System.Runtime")
clr.AddReference("System.Runtime.InteropServices")
clr.AddReference("DHI.Generic.MikeZero.DFS")
clr.AddReference("DHI.Generic.MikeZero.EUM")
# clr.AddReference('DHI.PFS')
# clr.AddReference('DHI.Projections')
clr.AddReference("DHI.Mike1D.Generic")
clr.AddReference("DHI.Mike1D.ResultDataAccess")
clr.AddReference("DHI.Mike1D.CrossSectionModule")
clr.AddReference("DHI.Mike1D.MikeIO")

from .res1d import Res1D
