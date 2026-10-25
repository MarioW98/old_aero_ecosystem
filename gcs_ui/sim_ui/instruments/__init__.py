from .base import BaseInstrument, UnitButtonsMixin, PlaceholderInstrument, TurnTargetMixin, ColorSelectorMixin
from .circular import CircularGauge
# from .specific import (
#     AirspeedIndicator, Altimeter, DigitalAltimeter,
#     AttitudeIndicator, AttitudeIndicatorFull, AttitudeIndicatorSquare,
#     RPMGauge, OilTempGauge, HeadingIndicator, DigitalVSI, TurnCoordinator,
# )
from .gauges import (
            AirspeedIndicator, Altimeter, RPMGauge, OilTempGauge,
            HeadingIndicator,TurnCoordinator,
            )
from .digital import (
            DigitalAltimeter, DigitalVSI
        )
from .attitude import (
            AttitudeIndicator, AttitudeIndicatorFull, AttitudeIndicatorSquare
        )

from .professional import (
    AirspeedIndicatorProfessional,
    HeadingIndicatorProfessional,
    AltimeterProfessional,
    VSIGaugeProfessional, TurnCoordinatorProfessional,
)
from .advance_instr import AttitudeAdvance, PrimaryFlightDisplay
from .comfort_instr import (
    AirspeedComfort, AltimeterComfort, VSIComfort, 
    HeadingComfort, TurnCoordinatorComfort,
)
from .viewport import SimulatorViewport

from .view_instr import (
    AirspeedTape, AltimeterTape, HeadingTape,
)


from .factory import InstrumentFactory
