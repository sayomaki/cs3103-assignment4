import matplotlib.pyplot as plt
import json

def generate_and_save_graphs(name, data):
    time = [d["elapsed_time"] for d in data]
    loss = [d["loss_rate"] * 100 for d in data]  # percentage
    throughput_bps = [d["tx_mbps"] * 125000 for d in data]  # convert to bytes/s
    rtt_avg = [d["rtt_avg"] * 1000 for d in data]  # seconds -> ms
    jitter = [abs(d["rtt_latest"] - d["rtt_avg"]) * 1000 for d in data]  # ms

    plt.rcParams.update({
        'font.size': 12,
        'figure.figsize': (8, 6),
        'axes.grid': True,
        'grid.alpha': 0.3,
        'lines.linewidth': 2,
        'legend.frameon': True,
        'legend.fontsize': 11
    })

    # Throughput + Packet Loss
    fig, ax1 = plt.subplots()

    color1, color2 = 'tab:blue', 'tab:red'
    line1, = ax1.plot(time, throughput_bps, color=color1, marker='o', label="Throughput (Bytes/s)")
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Throughput (Bytes/s)", color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)

    ax2 = ax1.twinx()
    line2, = ax2.plot(time, loss, color=color2, marker='x', linestyle='--', label="Packet Loss (%)")
    ax2.set_ylabel("Packet Loss (%)", color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)

    # plt.title("Throughput and Packet Loss Over Time", fontweight='bold', pad=30)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(f"output/{name}_throughput_loss.png", dpi=300)
    # plt.show()

    # RTT + Jitter
    fig, ax1 = plt.subplots()

    color1, color2 = 'tab:green', 'tab:orange'
    line1, = ax1.plot(time, rtt_avg, color=color1, marker='o', label="RTT (ms)")
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("RTT (ms)", color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)

    ax2 = ax1.twinx()
    line2, = ax2.plot(time, jitter, color=color2, marker='x', linestyle='--', label="Jitter (ms)")
    ax2.set_ylabel("Jitter (ms)", color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)

    # plt.title("RTT and Jitter Over Time", fontweight='bold', pad=30)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(f"output/{name}_rtt_jitter.png", dpi=300)
    # plt.show()

datasets = ['2_loss', '5_loss', '10_loss', 'vanilla']
for datatype in ['reliable', 'unreliable']:
    for dataset in datasets:
        with open(f'data/{datatype}_{dataset}.json', 'r') as f:
            data = json.loads(f.read())
        
        generate_and_save_graphs(f'{datatype}_{dataset}', data)
