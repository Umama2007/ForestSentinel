"""ForestSentinel: Real-data satellite pipeline and analytical intelligence system.

Part 1: Active-fire / thermal-anomaly ETL from NASA FIRMS to Firebase Cloud Firestore.
Part 2: Exploratory Data Analysis, Hotspot Tessellation & Explainable Priority-Zone Scoring.
"""

__version__ = "0.3.0"
__author__ = "ForestSentinel Team"

from forestsentinel.analysis_pipeline import ForestSentinelAnalysis
from forestsentinel.analysis_reporter import generate_analysis_report
from forestsentinel.analytics_repository import AnalyticsRepository, NoDataError
from forestsentinel.analyzer import FireActivityAnalyzer
from forestsentinel.config import Config, load_config
from forestsentinel.conservation_analyzer import ConservationAnalyzer
from forestsentinel.conservation_pipeline import ConservationPipeline
from forestsentinel.conservation_reporter import generate_conservation_report
from forestsentinel.conservation_repository import ConservationRepository
from forestsentinel.conservation_scoring import ConservationScorer
from forestsentinel.conservation_visualizer import ConservationVisualizer
from forestsentinel.extractor import ExtractionError, FirmsExtractor
from forestsentinel.firebase_client import FirebaseClient, FirebaseConfigError
from forestsentinel.gbif_client import GBIFAPIError, GBIFClient
from forestsentinel.iucn_client import IUCNClient
from forestsentinel.pipeline import ForestSentinelETL
from forestsentinel.priority_scoring import PriorityScorer
from forestsentinel.reporter import generate_etl_report
from forestsentinel.schemas import FireDetection, validate_fire_records
from forestsentinel.transformer import FirmsTransformer
from forestsentinel.visualizer import Visualizer

__all__ = [
    # Configuration
    "Config",
    "load_config",
    # Part 1: ETL Pipeline
    "FirmsExtractor",
    "ExtractionError",
    "FirmsTransformer",
    "FireDetection",
    "validate_fire_records",
    "FirebaseClient",
    "FirebaseConfigError",
    "generate_etl_report",
    "ForestSentinelETL",
    # Part 2: Analytics & EDA
    "AnalyticsRepository",
    "NoDataError",
    "FireActivityAnalyzer",
    "PriorityScorer",
    "Visualizer",
    "generate_analysis_report",
    "ForestSentinelAnalysis",
    # Part 3: Conservation Exposure Analysis
    "GBIFClient",
    "GBIFAPIError",
    "IUCNClient",
    "ConservationRepository",
    "ConservationScorer",
    "ConservationAnalyzer",
    "ConservationVisualizer",
    "generate_conservation_report",
    "ConservationPipeline",
]

