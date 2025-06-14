import random
import numpy as np
import pandas as pd
import simpy
from sim_tools.distributions import Exponential, Lognormal

class g:
    n_cubicles = 4
    trauma_treat_mean = 40
    trauma_treat_var = 5

    arrival_rate = 5

    sim_duration = 60 * 24 * 5 # 5 days
    number_of_runs = 10

class Patient:
    '''
    Class defining details for a patient entity
    '''
    def __init__(self, p_id):
        self.identifier = p_id
        self.arrival = -np.inf
        self.wait_treat = -np.inf
        self.total_time = -np.inf
        self.treat_duration = -np.inf

# Class representing our model of the clinic.
class Model:
    # Constructor to set up the model for a run.  We pass in a run number when
    # we create a new model.
    def __init__(self, run_number, seed_sequence):
        # Create a SimPy environment in which everything will live
        self.env = simpy.Environment()

        self.event_log = []

        self.patient_counter = 0

        self.patients = []

        self.init_resources()

        self.run_number = run_number

        self.results_df = pd.DataFrame()
        self.results_df["Patient ID"] = [1]
        self.results_df["Queue Time Cubicle"] = [0.0]
        self.results_df["Time with Nurse"] = [0.0]
        self.results_df.set_index("Patient ID", inplace=True)

        self.mean_q_time_cubicle = 0

        self.seed_sequence = seed_sequence[0].spawn(2)


        self.patient_inter_arrival_dist = Exponential(
            mean = g.arrival_rate,
            random_seed = self.seed_sequence[0]
            )

        self.treat_dist = Lognormal(
            mean = g.trauma_treat_mean,
            stdev = g.trauma_treat_var,
            random_seed = self.seed_sequence[1]
            )

    def init_resources(self):
        self.treatment_cubicles = simpy.Resource(self.env, capacity=g.n_cubicles)

    def generator_patient_arrivals(self):

        while True:
            self.patient_counter += 1

            p = Patient(self.patient_counter)

            self.patients.append(p)

            self.env.process(self.attend_clinic(p))

            sampled_inter = self.patient_inter_arrival_dist.sample()

            yield self.env.timeout(sampled_inter)

    def attend_clinic(self, patient):
        self.arrival = self.env.now
        self.event_log.append(
            {'entity_id': patient.identifier,
             'pathway': 'Simplest',
             'event_type': 'arrival_departure',
             'event': 'arrival',
             'time': self.env.now}
        )

        # request examination resource
        start_wait = self.env.now
        self.event_log.append(
            {'entity_id': patient.identifier,
             'pathway': 'Simplest',
             'event': 'treatment_wait_begins',
             'event_type': 'queue',
             'time': self.env.now}
        )

        # Seize a treatment resource when available
        with self.treatment_cubicles.request() as req:
            yield req

            # record the waiting time for registration
            self.wait_treat = self.env.now - start_wait
            self.event_log.append(
                {'entity_id': patient.identifier,
                    'pathway': 'Simplest',
                    'event': 'treatment_begins',
                    'event_type': 'resource_use',
                    'time': self.env.now,
                    }
            )

            # sample treatment duration
            self.treat_duration = self.treat_dist.sample()
            yield self.env.timeout(self.treat_duration)

            self.event_log.append(
                {'entity_id': patient.identifier,
                    'pathway': 'Simplest',
                    'event': 'treatment_complete',
                    'event_type': 'resource_use_end',
                    'time': self.env.now
                    }
                 )


        # total time in system
        self.total_time = self.env.now - self.arrival
        self.event_log.append(
            {'entity_id': patient.identifier,
            'pathway': 'Simplest',
            'event': 'depart',
            'event_type': 'arrival_departure',
            'time': self.env.now}
        )

    def calculate_run_results(self):
        # Take the mean of the queuing times across patients in this run of the
        # model.
        self.mean_q_time_cubicle = self.results_df["Queue Time Cubicle"].mean()

    def run(self):
        self.env.process(self.generator_patient_arrivals())

        self.env.run(until=g.sim_duration)

        self.calculate_run_results()

        self.event_log = pd.DataFrame(self.event_log)

        self.event_log["run"] = self.run_number

        return {'results': self.results_df, 'event_log': self.event_log}

class Trial:
    def  __init__(self, master_seed=42):
        self.df_trial_results = pd.DataFrame()
        self.df_trial_results["Run Number"] = [0]
        self.df_trial_results["Arrivals"] = [0]
        self.df_trial_results["Mean Queue Time Cubicle"] = [0.0]
        self.df_trial_results.set_index("Run Number", inplace=True)

        self.all_event_logs = []

        self.master_seed = master_seed
        self.seed_sequence = np.random.SeedSequence(entropy=self.master_seed)

    # Method to run a trial
    def run_trial(self, **kwargs):

        for run in range(g.number_of_runs):
            random.seed(run)

            my_model = Model(run, seed_sequence=self.seed_sequence.spawn(1),
                             **kwargs)

            model_outputs = my_model.run()
            patient_level_results = model_outputs["results"]
            event_log = model_outputs["event_log"]

            self.df_trial_results.loc[run] = [
                len(patient_level_results),
                my_model.mean_q_time_cubicle,
            ]

            self.all_event_logs.append(event_log)

        self.all_event_logs = pd.concat(self.all_event_logs)
